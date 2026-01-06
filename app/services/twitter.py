"""
Twitter monitoring service using twscrape.
Polls followed Twitter accounts and forwards new tweets to VIP channel.
"""

import asyncio
import json
import random
from typing import Dict, List, Optional
from datetime import datetime

from app.core.config import settings
from app.core.database import db
from app.core.logger import Logger

logger = Logger("TwitterService")


class TwitterService:
    def __init__(self):
        self.is_running = False
        self.api = None
        self.follows: Dict[str, dict] = {}  # username -> {user_id, last_tweet_id, enabled}
        self._poll_task = None
        # Random interval between 3-7 minutes to avoid detection
        self.min_interval = 180  # 3 minutes
        self.max_interval = 420  # 7 minutes
    
    async def initialize(self):
        """Initialize Twitter API and load follows from database."""
        logger.info("Initializing TwitterService...")
        
        # Check for credentials
        if not settings.TWITTER_ACCOUNTS:
            logger.warn("TWITTER_ACCOUNTS not configured. Twitter monitoring disabled.")
            return False
        
        try:
            from twscrape import API
            self.api = API()
            
            # Parse and add accounts
            accounts = json.loads(settings.TWITTER_ACCOUNTS)
            for acc in accounts:
                username = acc.get('username')
                password = acc.get('password')
                email = acc.get('email')
                email_password = acc.get('email_password')
                cookies = acc.get('cookies')
                
                if cookies:
                    # Add with cookies (more stable)
                    await self.api.pool.add_account(username, password or "", email or "", email_password or "", cookies=cookies)
                    logger.info(f"Added Twitter account (cookies): {username}")
                elif username and password and email:
                    # Add with login credentials
                    await self.api.pool.add_account(username, password, email, email_password or "")
                    logger.info(f"Added Twitter account: {username}")
            
            # Login all accounts
            await self.api.pool.login_all()
            logger.info("Twitter accounts logged in")
            
        except Exception as e:
            logger.error(f"Failed to initialize Twitter API: {e}")
            return False
        
        # Load follows from database
        if db.pool:
            try:
                rows = await db.pool.fetch("SELECT username, user_id, last_tweet_id, enabled FROM twitter_follows")
                for row in rows:
                    self.follows[row['username']] = {
                        'username': row['username'],
                        'user_id': row['user_id'],
                        'last_tweet_id': row['last_tweet_id'],
                        'enabled': row['enabled']
                    }
                logger.info(f"Loaded {len(rows)} Twitter follows from database")
            except Exception as e:
                logger.warn(f"Failed to load Twitter follows: {e}")
        
        logger.info("TwitterService initialized")
        return True
    
    async def start(self):
        """Start the polling loop."""
        if self.is_running or not self.api:
            return
        
        self.is_running = True
        self._poll_task = asyncio.create_task(self._poll_loop())
        logger.info("🐦 Twitter monitoring started")
    
    async def stop(self):
        """Stop the polling loop."""
        self.is_running = False
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
        logger.info("Twitter monitoring stopped")
    
    async def _poll_loop(self):
        """Main polling loop with random intervals."""
        while self.is_running:
            try:
                await self._check_all_follows()
                
                # Random wait to avoid detection
                wait_seconds = random.randint(self.min_interval, self.max_interval)
                logger.debug(f"Next Twitter poll in {wait_seconds}s")
                await asyncio.sleep(wait_seconds)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in Twitter poll loop: {e}")
                await asyncio.sleep(60)
    
    async def _check_all_follows(self):
        """Check all followed accounts for new tweets."""
        for username, info in self.follows.items():
            if not info.get('enabled', True):
                continue
            
            try:
                await self._check_user_tweets(username, info)
                # Small delay between users to avoid rate limiting
                await asyncio.sleep(random.randint(2, 5))
            except Exception as e:
                logger.warn(f"Failed to check tweets for @{username}: {e}")
    
    async def _check_user_tweets(self, username: str, info: dict):
        """Check a single user for new tweets."""
        from twscrape import gather
        
        user_id = info.get('user_id')
        last_tweet_id = info.get('last_tweet_id')
        
        # Get user_id if not cached
        if not user_id:
            try:
                user = await self.api.user_by_login(username)
                if user:
                    user_id = str(user.id)
                    info['user_id'] = user_id
                    await self._update_follow(username, user_id=user_id)
            except Exception as e:
                logger.warn(f"Failed to get user_id for @{username}: {e}")
                return
        
        if not user_id:
            return
        
        # Get recent tweets
        try:
            tweets = await gather(self.api.user_tweets(int(user_id), limit=5))
            
            if not tweets:
                return
            
            # Filter new tweets
            new_tweets = []
            for tweet in tweets:
                tweet_id = str(tweet.id)
                if last_tweet_id and int(tweet_id) <= int(last_tweet_id):
                    break
                new_tweets.append(tweet)
            
            if new_tweets:
                # Update last_tweet_id
                newest_id = str(new_tweets[0].id)
                info['last_tweet_id'] = newest_id
                await self._update_follow(username, last_tweet_id=newest_id)
                
                # Forward new tweets (oldest first)
                for tweet in reversed(new_tweets):
                    await self._forward_tweet(username, tweet)
                    
        except Exception as e:
            logger.warn(f"Failed to get tweets for @{username}: {e}")
    
    async def _forward_tweet(self, username: str, tweet):
        """Forward a tweet to VIP channel."""
        from app.core.bot import telegram_service
        
        target = settings.VIP_TARGET_CHANNEL or settings.TARGET_CHANNEL
        if not target:
            return
        
        # Format tweet
        tweet_url = f"https://twitter.com/{username}/status/{tweet.id}"
        text = tweet.rawContent or ""
        
        # Truncate if too long
        if len(text) > 3500:
            text = text[:3500] + "..."
        
        formatted = (
            f"🐦 <b>@{username}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"{text}\n\n"
            f"🔗 <a href='{tweet_url}'>View on Twitter</a>"
        )
        
        try:
            if isinstance(target, str) and (target.isdigit() or target.lstrip('-').isdigit()):
                target = int(target)
            
            await telegram_service.send_message(target, formatted, parse_mode='html')
            logger.info(f"📤 Forwarded tweet from @{username}")
        except Exception as e:
            logger.error(f"Failed to forward tweet: {e}")
    
    async def _update_follow(self, username: str, user_id: str = None, last_tweet_id: str = None):
        """Update follow in database."""
        if not db.pool:
            return
        
        try:
            if user_id:
                await db.pool.execute(
                    "UPDATE twitter_follows SET user_id = $2 WHERE username = $1",
                    username, user_id
                )
            if last_tweet_id:
                await db.pool.execute(
                    "UPDATE twitter_follows SET last_tweet_id = $2 WHERE username = $1",
                    username, last_tweet_id
                )
        except Exception as e:
            logger.warn(f"Failed to update follow: {e}")
    
    # ─────────────────────────────────────────────────────────────────────────
    # Follow Management
    # ─────────────────────────────────────────────────────────────────────────
    
    async def add_follow(self, username: str) -> bool:
        """Add a Twitter account to follow."""
        username = username.lstrip('@').lower()
        
        if username in self.follows:
            return False
        
        self.follows[username] = {
            'username': username,
            'user_id': None,
            'last_tweet_id': None,
            'enabled': True
        }
        
        if db.pool:
            try:
                await db.pool.execute(
                    "INSERT INTO twitter_follows (username, enabled) VALUES ($1, TRUE) ON CONFLICT (username) DO NOTHING",
                    username
                )
            except Exception as e:
                logger.warn(f"Failed to save follow: {e}")
        
        logger.info(f"🐦 Added Twitter follow: @{username}")
        return True
    
    async def remove_follow(self, username: str) -> bool:
        """Remove a Twitter follow."""
        username = username.lstrip('@').lower()
        
        if username not in self.follows:
            return False
        
        del self.follows[username]
        
        if db.pool:
            try:
                await db.pool.execute("DELETE FROM twitter_follows WHERE username = $1", username)
            except Exception as e:
                logger.warn(f"Failed to remove follow: {e}")
        
        logger.info(f"🗑️ Removed Twitter follow: @{username}")
        return True
    
    async def toggle_follow(self, username: str, enabled: bool):
        """Enable or disable a follow."""
        username = username.lstrip('@').lower()
        
        if username in self.follows:
            self.follows[username]['enabled'] = enabled
            
            if db.pool:
                try:
                    await db.pool.execute(
                        "UPDATE twitter_follows SET enabled = $2 WHERE username = $1",
                        username, enabled
                    )
                except Exception as e:
                    logger.warn(f"Failed to toggle follow: {e}")


twitter_service = TwitterService()

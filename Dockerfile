FROM node:20-alpine

WORKDIR /app

# Install dependencies
COPY package*.json ./
RUN npm ci --omit=dev

# Copy source
COPY src ./src/

# Environment variables should be provided at runtime
# CMD to run the bot
CMD ["npm", "start"]

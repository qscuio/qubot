# Build stage
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci

# Production stage
FROM node:20-alpine
WORKDIR /app

# Install git for /export command and curl for runtime/debug probes
RUN apk add --no-cache git openssh-client curl

# Install production dependencies only
COPY package*.json ./
RUN npm ci --omit=dev

# Copy source code
COPY src ./src/
COPY web ./web/
COPY scripts ./scripts/

# Health check (optional - bot doesn't have HTTP endpoint by default)
# HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
#   CMD node -e "console.log('ok')"

CMD ["npm", "start"]

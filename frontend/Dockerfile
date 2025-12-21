# syntax=docker/dockerfile:1

# =============================================================================
# Arquivo da Violência Frontend - Production Dockerfile
# =============================================================================

# Build stage
FROM node:20-alpine AS builder

WORKDIR /app

# Copy package files
COPY package.json package-lock.json ./

# Install dependencies
RUN npm ci

# Copy source code
COPY . .

# Build the app (Vite will embed VITE_* env vars at build time)
RUN npm run build

# =============================================================================
# Production stage - Nginx
# =============================================================================
FROM nginx:alpine AS production

# Allow specifying which nginx config to use (default: nginx.conf)
ARG NGINX_CONF=nginx.conf

# Copy custom nginx config
COPY ${NGINX_CONF} /etc/nginx/conf.d/default.conf

# Copy built assets from builder
COPY --from=builder /app/dist /usr/share/nginx/html

# Expose port 80
EXPOSE 80

# Start nginx
CMD ["nginx", "-g", "daemon off;"]


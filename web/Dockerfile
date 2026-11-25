# syntax=docker/dockerfile:1
FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:22-alpine AS build
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
# Rewrites are resolved at build time: where the browser's /api/v1 calls are proxied to.
ARG API_URL=http://api:8000
ENV API_URL=$API_URL
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:22-alpine AS run
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
RUN addgroup -S rafta && adduser -S rafta -G rafta
COPY --from=build --chown=rafta:rafta /app/.next/standalone ./
COPY --from=build --chown=rafta:rafta /app/.next/static ./.next/static
USER rafta
EXPOSE 3000
CMD ["node", "server.js"]

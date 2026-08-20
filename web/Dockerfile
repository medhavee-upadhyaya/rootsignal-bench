FROM node:22.22.1-alpine AS builder
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:22.22.1-alpine AS runtime
ENV NODE_ENV=production \
    PORT=3000 \
    HOST=0.0.0.0
WORKDIR /app
RUN addgroup -S -g 10001 rootsignal && adduser -S -u 10001 -G rootsignal rootsignal
COPY --from=builder --chown=rootsignal:rootsignal /app /app
USER 10001:10001
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD wget -q --spider http://127.0.0.1:3000/ || exit 1
CMD ["npm", "run", "start"]

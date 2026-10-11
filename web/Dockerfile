FROM node:22.22.1-alpine AS builder
ARG ROOTSIGNAL_BASE_PATH=""
ENV ROOTSIGNAL_BASE_PATH=$ROOTSIGNAL_BASE_PATH
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:22.22.1-alpine AS runtime
ARG ROOTSIGNAL_BASE_PATH=""
ENV NODE_ENV=production \
    PORT=3000 \
    HOST=0.0.0.0 \
    ROOTSIGNAL_BASE_PATH=$ROOTSIGNAL_BASE_PATH
WORKDIR /app
RUN addgroup -S -g 10001 rootsignal && adduser -S -u 10001 -G rootsignal rootsignal
COPY --from=builder --chown=rootsignal:rootsignal /app /app
USER 10001:10001
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD wget -q --spider "http://127.0.0.1:3000${ROOTSIGNAL_BASE_PATH:-}/" || exit 1
CMD ["npm", "run", "start"]

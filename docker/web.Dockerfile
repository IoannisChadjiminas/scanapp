# The build stage only produces static files, so it runs on the builder's own
# platform; a multi-arch build (linux/amd64,linux/arm64) emulates only Caddy.
FROM --platform=$BUILDPLATFORM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM caddy:2.10-alpine
COPY docker/Caddyfile /etc/caddy/Caddyfile
COPY --from=build /app/out /srv
EXPOSE 80 443

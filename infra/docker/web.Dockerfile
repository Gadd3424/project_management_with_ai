FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json pnpm-lock.yaml* pnpm-workspace.yaml ./
RUN npm install --global pnpm@10.17.1 \
    && pnpm install --frozen-lockfile

FROM deps AS build
ARG API_INTERNAL_URL=http://api:8000/api/v1
ENV API_INTERNAL_URL=${API_INTERNAL_URL}
COPY . .
RUN pnpm run build

FROM node:22-alpine
WORKDIR /app
ENV NODE_ENV=production
COPY --from=build /app/package.json ./package.json
COPY --from=build /app/node_modules ./node_modules
COPY --from=build /app/.next ./.next
COPY --from=build /app/public ./public
USER node
EXPOSE 3000
CMD ["node", "node_modules/next/dist/bin/next", "start"]

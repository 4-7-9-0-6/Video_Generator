# ToonForge frontend (Next.js 15). Build then serve with `next start`.
FROM node:20-slim AS build
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install
COPY . .
# Baked at build time; override per-deployment if the API isn't on localhost:8000.
ENV NEXT_PUBLIC_API_BASE=http://localhost:8000
RUN npm run build

FROM node:20-slim
WORKDIR /app
ENV NODE_ENV=production
COPY --from=build /app ./
EXPOSE 3000
CMD ["npm", "run", "start"]

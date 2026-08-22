# Build do SPA
FROM node:20-alpine AS build
WORKDIR /app
# URL pública da API, embutida no bundle em tempo de build (vazio = mesmo domínio, /api).
ARG VITE_API_URL=""
ENV VITE_API_URL=$VITE_API_URL
COPY package.json ./
RUN npm install
COPY . .
RUN npm run build

# Servir estático com nginx
FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80

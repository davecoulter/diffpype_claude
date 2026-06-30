FROM node:20-alpine

WORKDIR /app

COPY src/ui/package.json ./
RUN npm install

COPY src/ui .

CMD ["npm", "run", "dev"]

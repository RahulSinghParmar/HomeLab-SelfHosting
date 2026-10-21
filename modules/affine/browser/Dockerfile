FROM mcr.microsoft.com/playwright@sha256:06a9939e57531807f8d5fd76ce44b53165ffb7d7501d87ab10e285c20b1e971f

ENV NODE_ENV=production \
    PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
WORKDIR /validation
COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts --omit=dev --fund=false --audit=false \
    && npm cache clean --force
COPY validate.mjs ./validate.mjs
RUN mkdir /evidence && chown pwuser:pwuser /evidence
USER pwuser
ENTRYPOINT ["node", "/validation/validate.mjs"]

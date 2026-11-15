ARG CODE_SERVER_BASE=ghcr.io/coder/code-server:4.145.0@sha256:992796b850b8b7ec6f7393b8dd2295840a65cf5071981990ff41ef52dd566c43
FROM ${CODE_SERVER_BASE}

USER root

ARG TARGETARCH
ARG CODE_SERVER_VERSION=4.145.0
ARG CODE_SERVER_PLATFORM_DIGEST=unreviewed
ARG NODE_VERSION=24.19.0
ARG NODE_ARCHIVE_SHA256=unreviewed
ARG NODE_SHA256_AMD64=14b342e71204f811bde6153be8e04b62aef63c236fef92b55f9c83154b409647
ARG NODE_SHA256_ARM64=01443c1e1a29e531ccad5a46fefa6df490d2189c49f7955904aecdbb0fe86fdc

ENV DEBIAN_FRONTEND=noninteractive

RUN set -eux; \
    actual="$(code-server --version 2>&1 \
        | sed -n '/^[0-9][0-9]*\.[0-9][0-9]*\.[0-9][0-9]*/{s/ .*//;p;q;}')"; \
    test "$actual" = "$CODE_SERVER_VERSION"

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential cargo clang cmake composer default-jdk-headless \
        fd-find fzf g++ gcc gdb gh git-lfs golang-go jq lldb make \
        mariadb-client maven ninja-build php-cli pipx pkg-config \
        postgresql-client python-is-python3 python3 python3-pip python3-venv \
        redis-tools ripgrep ruby-full rustc shellcheck sqlite3 tmux tree \
        unzip xz-utils zip \
    && ln -sf /usr/bin/fdfind /usr/local/bin/fd \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

RUN set -eux; \
    case "$TARGETARCH" in \
      amd64) node_arch=x64; node_sha="$NODE_SHA256_AMD64" ;; \
      arm64) node_arch=arm64; node_sha="$NODE_SHA256_ARM64" ;; \
      *) echo "Unsupported TARGETARCH: $TARGETARCH" >&2; exit 64 ;; \
    esac; \
    archive="node-v${NODE_VERSION}-linux-${node_arch}.tar.xz"; \
    curl -fsSLO "https://nodejs.org/dist/v${NODE_VERSION}/${archive}"; \
    echo "${node_sha}  ${archive}" | sha256sum --check --strict; \
    tar -xJf "$archive" -C /usr/local --strip-components=1 --no-same-owner; \
    rm "$archive"; \
    test "$(node --version)" = "v${NODE_VERSION}"

COPY --chmod=0755 install-extensions.sh /usr/local/bin/install-code-extensions
COPY --chmod=0755 start-code-server.sh /usr/local/bin/homelab-code-server
COPY extensions.txt /opt/homelab/extensions.txt
COPY settings.json /opt/homelab/settings.json

RUN mkdir -p /opt/homelab/extensions \
        /home/coder/.config /home/coder/.local /home/coder/.secure \
        /home/coder/project \
    && chown -R coder:coder /opt/homelab /home/coder/.config \
        /home/coder/.local /home/coder/.secure /home/coder/project \
    && chmod 0700 /home/coder/.secure

USER coder
RUN install-code-extensions /opt/homelab/extensions.txt /opt/homelab/extensions

WORKDIR /home/coder/project
LABEL org.homelab.code-server.version="${CODE_SERVER_VERSION}" \
      org.homelab.code-server.platform-digest="${CODE_SERVER_PLATFORM_DIGEST}" \
      org.homelab.node.version="${NODE_VERSION}" \
      org.homelab.node.archive-sha256="${NODE_ARCHIVE_SHA256}"
ENTRYPOINT ["/usr/local/bin/homelab-code-server"]
CMD ["--config", "/home/coder/.config/code-server/config.yaml", "/home/coder/project"]

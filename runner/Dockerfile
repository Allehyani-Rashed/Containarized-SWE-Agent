FROM debian:testing-slim

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bash \
        ca-certificates \
        curl \
        git \
        python3 \
        python3-venv \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --shell /bin/bash --uid 1000 codex

COPY runner/bin/codex /usr/local/bin/codex
COPY runner/bin/finish_task.sh /usr/local/bin/finish_task.sh
COPY runner/bin/launch_codex.sh /usr/local/bin/launch_codex.sh
COPY runner/bin/install_codex_agent.sh /usr/local/bin/install_codex_agent.sh
RUN chmod +x /usr/local/bin/codex /usr/local/bin/finish_task.sh /usr/local/bin/launch_codex.sh /usr/local/bin/install_codex_agent.sh

RUN mkdir -p /opt/codex/bin /opt/codex/bootstrap
COPY runner/codex_agent/ /opt/codex/bootstrap/
COPY .projectsanitize /opt/codex/bootstrap/projectsanitize-default
COPY codex-x86_64-unknown-linux-gnu.tar.gz /opt/codex/bootstrap/
RUN install -m 0755 /opt/codex/bootstrap/codex /opt/codex/bin/codex

ARG CODEX_AGENT_TARBALL="codex-x86_64-unknown-linux-gnu.tar.gz"
ARG CODEX_AGENT_URL=""
ARG CODEX_AGENT_PINNED_VERSION=""
ARG CODEX_AGENT_PINNED_URL=""
ARG CODEX_AGENT_PINNED_SHA256=""
ARG CODEX_AGENT_AUTO_DOWNLOAD=1
ARG CODEX_AGENT_FORCE_DOWNLOAD=0
ENV CODEX_AGENT_PINNED_VERSION=${CODEX_AGENT_PINNED_VERSION} \
    CODEX_AGENT_PINNED_URL=${CODEX_AGENT_PINNED_URL} \
    CODEX_AGENT_PINNED_SHA256=${CODEX_AGENT_PINNED_SHA256} \
    CODEX_AGENT_AUTO_DOWNLOAD=${CODEX_AGENT_AUTO_DOWNLOAD} \
    CODEX_AGENT_FORCE_DOWNLOAD=${CODEX_AGENT_FORCE_DOWNLOAD}
RUN /usr/local/bin/install_codex_agent.sh "${CODEX_AGENT_TARBALL}" "${CODEX_AGENT_URL}"

ENV PATH="/opt/codex/bin:${PATH}"

USER codex
WORKDIR /home/codex

ENTRYPOINT ["/bin/bash", "-lc"]
CMD ["sleep infinity"]

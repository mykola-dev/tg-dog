FROM docker.n8n.io/n8nio/n8n:2.13.2

USER root
RUN mkdir -p /bootstrap /home/node/.n8n && chown -R node:node /bootstrap /home/node/.n8n

USER node
ENTRYPOINT ["tini", "--", "/bin/sh", "/bootstrap/bootstrap.sh"]

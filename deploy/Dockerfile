ARG SOURCE_DATE_EPOCH=0
FROM elixir:1.20.4-otp-29-alpine@sha256:f1a8c06b332cacc7239381a25331a807fb63962f8221dff545ea4d8f78b0f50c AS compiler
ADD payload.tar /
ADD packaging.tar /
ENV ERL_FLAGS="+S 2:2" HOME=/tmp
RUN ["elixir", "/packaging/build.exs"]

FROM elixir:1.20.4-otp-29-alpine@sha256:f1a8c06b332cacc7239381a25331a807fb63962f8221dff545ea4d8f78b0f50c
LABEL org.opencontainers.image.title="ADHD coordination hub"
LABEL org.opencontainers.image.licenses="Apache-2.0"
ADD payload.tar /
COPY --from=compiler /runtime/adhd /runtime/adhd
# COPY creates its destination parents with wall-clock metadata.
RUN chmod 0555 /runtime/adhd && touch -d @0 /runtime /runtime/adhd
WORKDIR /app
ENV ERL_FLAGS="+S 2:2" HOME=/tmp
USER 10001:10001
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 CMD ["elixir", "/app/health.exs"]
STOPSIGNAL SIGTERM
ENTRYPOINT ["elixir", "/runtime/adhd/boot.exs", "/app/hub.exs"]
CMD ["[\"serve\",\"/config/hub.json\"]"]

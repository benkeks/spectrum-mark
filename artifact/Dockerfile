FROM node:22.14.0-bookworm-slim AS node
FROM sbtscala/scala-sbt:eclipse-temurin-17.0.15_6_1.12.2_2.13.18@sha256:5df96d8d12cc065d8688fb9fd8374a9bebea5a82977db339aca29b2811b2d4c5 AS tools

USER root
COPY --from=node /usr/local/ /usr/local/
RUN sed -i 's|^URIs:.*|URIs: https://snapshot.ubuntu.com/ubuntu/20251001T000000Z/|' /etc/apt/sources.list.d/ubuntu.sources \
    && apt-get -o Acquire::Check-Valid-Until=false update \
    && apt-get install -y --no-install-recommends build-essential cmake libboost-dev python3 busybox tcsh time \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/spectrum-mark
COPY mcrl2/ mcrl2/
COPY build_mcrl2.sh .
ARG JOBS=2
RUN JOBS="$JOBS" bash build_mcrl2.sh
COPY equivio/ equivio/
COPY artifact/PaperBenchmark.scala equivio/shared/src/main/scala-2.13/io/equiv/eqfiddle/artifact/PaperBenchmark.scala
RUN sed -i '/assembly \/ test := {}/a\  assembly / mainClass := Some("io.equiv.eqfiddle.tool.Benchmark"),' equivio/build.sbt
WORKDIR /opt/spectrum-mark/equivio
RUN sbt -batch "shared/test" "shared/assembly" "jsApi/fastLinkJS" webStage \
    && node js-api/src/main/jstest/TestApi.js

FROM tools AS artifact
WORKDIR /opt/spectrum-mark
COPY *.py *.sh LICENSE README.md ./
COPY examples/*.csv examples/
COPY known-results/ known-results/
COPY artifact/ artifact/
RUN find . -type f -not -path './build/*' -not -path '*/target/*' \
    -print0 | sort -z | xargs -0 sha256sum > /opt/source-sha256.txt
RUN bash artifact/smoke-test.sh

ENV ARTIFACT_ROOT=/opt/spectrum-mark
EXPOSE 8080
ENTRYPOINT []
CMD ["busybox", "httpd", "-f", "-p", "8080", "-h", "/opt/spectrum-mark/equivio/web/target/web/stage"]

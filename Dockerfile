FROM python:3.12-alpine
ARG APK_MIRROR=
RUN if [ -n "$APK_MIRROR" ]; then sed -i "s|https://dl-cdn.alpinelinux.org/alpine|$APK_MIRROR|g" /etc/apk/repositories; fi && \
    apk add --no-cache ca-certificates tzdata
ENV TZ=Asia/Shanghai PYTHONUNBUFFERED=1 GOMEMLIMIT=96MiB GOMAXPROCS=2
WORKDIR /opt/cfdata/app
COPY bin/ /opt/cfdata/bin/
COPY tools/fetch_upstream.py /opt/cfdata/tools/fetch_upstream.py
RUN python3 /opt/cfdata/tools/fetch_upstream.py --system linux --directory /opt/cfdata/bin
COPY app/ /opt/cfdata/app/
COPY LICENSE NOTICE.md /opt/cfdata/
VOLUME ["/data"]
EXPOSE 13335
ENTRYPOINT ["python3", "/opt/cfdata/app/entrypoint.py"]

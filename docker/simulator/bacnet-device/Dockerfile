# Minimal BACnet/IP device for lab and CI (Who-Is / ReadProperty / WriteProperty presentValue).
FROM python:3.12-slim

WORKDIR /app
RUN pip install --no-cache-dir "bacpypes3>=0.0.80"

COPY server.py bbmd_runner.py probe_foreign_read.py /app/

ENV DEVICE_INSTANCE=21001
ENV BACNET_UDP_PORT=47808

EXPOSE 47808/udp

CMD ["python", "-u", "/app/server.py"]

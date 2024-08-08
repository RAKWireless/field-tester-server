root@loraserver01:/home/lora/raktester# cat Dockerfile
FROM python:3.10-alpine3.17

##uncomment to add proxy
#ENV HTTPS_PROXY http://username:password@proxy:port
#ENV HTTP_PROXY http://username:password@proxy:port

WORKDIR /app
ADD server.py requirements.txt  ./
RUN pip install -r requirements.txt
RUN pip install "cython<3.0.0" && pip install --no-build-isolation pyyaml==6.0

CMD ["python", "server.py"]

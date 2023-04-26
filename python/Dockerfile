FROM python:3.10-alpine3.17

WORKDIR /app
ADD server.py requirements.txt  ./
RUN pip install -r requirements.txt

CMD ["python", "server.py"]

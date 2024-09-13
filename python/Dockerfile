FROM python:3.12.6-alpine3.20

WORKDIR /app
ADD server.py requirements.txt  ./
RUN pip install -r requirements.txt

CMD ["python", "server.py"]

FROM python:3.12-alpine

RUN apk add --no-cache curl

WORKDIR /nntp_reader

COPY requirements.freeze.txt /nntp_reader
RUN pip install --no-cache-dir -r requirements.freeze.txt

COPY . /nntp_reader

EXPOSE 8080

CMD ["python", "main.py"]

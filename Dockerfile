FROM python:3.12-alpine

RUN apk add --no-cache curl

WORKDIR /app

COPY requirements.freeze.txt ./
RUN pip install --no-cache-dir -r requirements.freeze.txt

COPY . ./

EXPOSE 8080

CMD ["python", "main.py"]

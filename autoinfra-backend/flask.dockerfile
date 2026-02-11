FROM mcr.microsoft.com/azure-cli:latest-amd64

RUN curl -sS https://bootstrap.pypa.io/get-pip.py -o get-pip.py && \
    python3 get-pip.py && \
    rm get-pip.py

WORKDIR /app

COPY requirements.txt ./

RUN pip install -r requirements.txt

COPY . .

EXPOSE 8100

CMD ["gunicorn", "-w", "1", "--threads", "4", "--timeout", "120", "app:app", "-b", ":8100"]
#CMD ["flask", "run", "--host=0.0.0.0", "--port=8100"]
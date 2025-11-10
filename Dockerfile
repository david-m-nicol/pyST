FROM ubuntu:latest
WORKDIR /app

COPY iec_checker_Linux_x86_64 .
RUN chmod +x ./iec_checker_Linux_x86_64 
ENTRYPOINT ["./iec_checker_Linux_x86_64", "-i","st","-o","plain"]

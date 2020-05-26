FROM centos:7

ENV TZ=America/New_York
#ENV HTTP_PROXY=http://127.0.0.1:8080
#RUN echo "proxy=http://127.0.0.1:8080" >> /etc/yum.conf

RUN yum -y install epel-release

RUN yum -y install wget supervisor python36 python36-pip crontabs cronie && \
    yum clean all 

COPY influxdb-1.7.9.x86_64.rpm /tmp/

RUN cd /tmp && \
    wget wget https://dl.influxdata.com/influxdb/releases/influxdb-1.8.0.x86_64.rpm \
    yum -y localinstall influxdb-1.8.0.x86_64.rpm && \
    rm -rf  influxdb-1.8.0.x86_64.rpm && \
    mkdir /njmon && \
    yum clean all

COPY *.py /njmon/
COPY njmond.conf /njmon/
COPY *.ini /etc/supervisord.d/ 
#COPY start.sh /root
COPY entrypoint.sh /root
COPY nmon2influxdb /njmon
COPY .nmon2influxdb.cfg /root/
COPY hmc_collector.sh /njmon

RUN python3 -m pip install  --upgrade pip && \
    python3 -m pip install  influxdb && \
    chmod 755 /njmon/*.py

#ENV HTTP_PROXY=

VOLUME /var/lib/influxdb
VOLUME /njmon

EXPOSE 8086  8181 

ENTRYPOINT /root/entrypoint.sh
#CMD ["/bin/bash", "/root/entrypoint.sh"]

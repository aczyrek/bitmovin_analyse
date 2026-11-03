FROM public.ecr.aws/lambda/python:3.12

# Zależności najpierw — dzięki temu cache warstw działa przy zmianach w kodzie
COPY requirements.txt ${LAMBDA_TASK_ROOT}/
RUN pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements.txt

COPY app.py bitmovin_report.py google_drive_helper.py handler.py ${LAMBDA_TASK_ROOT}/

# Domyślnie handler HTTP (Function URL). Funkcja z harmonogramu nadpisuje CMD
# na handler.scheduled_report_handler w template.yaml.
CMD ["handler.lambda_handler"]

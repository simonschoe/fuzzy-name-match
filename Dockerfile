# Use a base image with Python installed
FROM python:3.8.5-slim

#ARG GRADIO_SERVER_PORT=7860
#ENV GRADIO_SERVER_PORT=${GRADIO_SERVER_PORT}

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file to the container
COPY requirements.txt /app/

# Install the required dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the Gradio app files to the container
COPY main.py /app/

# Expose the port that the Gradio app will run on
EXPOSE 7878

# Set the entrypoint command to run the Gradio app
CMD ["python", "/app/main.py"]

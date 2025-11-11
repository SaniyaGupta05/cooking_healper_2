# ------------------------------------------------------------
# Project: Cooking Helper
# Abstract: This container runs a Flask-based health & recipe
#           management web application with Groq AI integration.
# Type of Users: End-users, Nutritionists, Health app testers
# Description: Provides meal planning, recipe suggestions, 
#              and personalized health assistance.
# ------------------------------------------------------------

FROM python:3.9-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 5000
WORKDIR /app/app
CMD python app.py

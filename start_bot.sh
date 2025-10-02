#!/bin/bash

# SafetyBot Startup Script for Ubuntu
# This script sets up the environment and starts the bot

echo "Starting SafetyBot setup..."

# Check if Python 3 is installed
if ! command -v python3 &> /dev/null; then
    echo "Python 3 is not installed. Please install Python 3.8+ first."
    exit 1
fi

# Check if pip is installed
if ! command -v pip3 &> /dev/null; then
    echo "pip3 is not installed. Installing pip..."
    sudo apt update
    sudo apt install python3-pip -y
fi

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Install requirements
echo "Installing Python dependencies..."
pip install -r requirements.txt

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo "Error: .env file not found!"
    echo "Please create a .env file with your configuration."
    exit 1
fi

# Make the Python script executable
chmod +x safetybot.py

# Start the bot
echo "Starting SafetyBot..."
echo "Press Ctrl+C to stop the bot"
python3 safetybot.py
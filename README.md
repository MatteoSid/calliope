# Calliope
Calliope is a Telegram Bot that transcribe any audio or video mesage using Whisper from OpenAi.

### Why should you use Calliope to transcribe messages? 
There are many bots that can do this, but this means that you have to forward your messages to someone who can read and listen to everything you send them. Additionally, if you add a bot to a group and set it as an administrator, it can read everything that is written within the group. With Calliope, you can start your own private bot that runs on your computer so you can transcribe all your messages without having to give private information to anyone.

## Screenshots

<p align="center">
  <img src="screenshots\screenshot.jpg" alt="image" width="300">
</p>

## Setup
Whisper used Python 3.9.9 and [PyTorch](https://pytorch.org/) 1.10.1 to train and test the models, but the codebase is expected to be compatible with Python 3.8-3.10 and recent PyTorch versions. The codebase also depends on a few Python packages, most notably [OpenAI's tiktoken](https://github.com/openai/tiktoken) for their fast tokenizer implementation and [ffmpeg-python](https://github.com/kkroening/ffmpeg-python) for reading audio files.

### Packages installation
    pip install -r requirements.txt

It also requires the command-line tool [`ffmpeg`](https://ffmpeg.org/) to be installed on your system, which is available from most package managers:

```bash
# on Ubuntu or Debian
sudo apt update && sudo apt install ffmpeg

# on Arch Linux
sudo pacman -S ffmpeg

# on MacOS using Homebrew (https://brew.sh/)
brew install ffmpeg

# on Windows using Chocolatey (https://chocolatey.org/)
choco install ffmpeg

# on Windows using Scoop (https://scoop.sh/)
scoop install ffmpeg
```

## Create a Telegram bot using BotFather

1. Open the Telegram app and search for the **BotFather**. It's a bot created by the Telegram team to help users create their own bots.
2. Start a chat with the BotFather and send the command `/newbot` to create a new bot.
3. Follow the instructions provided by the BotFather to set up your bot. You'll need to choose a name and username for your bot.
4. Once you've completed the setup process, the BotFather will provide you with a **token** for your bot. This token is used to authenticate your bot and send requests to the Telegram API.

That's it! You've successfully created a Telegram bot using BotFather. You can now start Calliope using the token you just received.

## Starting Calliope
You can start Calliope with

    python calliope.py

At the first launch you have to provide the token previously provided from BotFather. The token will be saved in the `TOKEN.txt` file. You can delete this file for run Calliope with another bot.

## Usage
You can forward any voice or video message to your bot runnig Calliope or you can add your bot to a group and set it as administrator for automatically convert any voice or video message to a text.
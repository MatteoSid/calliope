# Calliope
[![](https://img.shields.io/badge/license-MIT-brightgreen.svg)](https://github.com/ptkdev/chrome-extension-aspectratio219/blob/nightly/LICENSE.md)

Calliope is a Telegram Bot that transcribe any audio or video mesage using Whisper from OpenAi.

### Why should you use Calliope to transcribe messages? 
There are many bots that can do this, but this means that you have to forward your messages to someone who can read and listen to everything you send them. Additionally, if you add a bot to a group and set it as an administrator, it can read everything that is written within the group. With Calliope, you can start your own private bot that runs on your computer so you can transcribe all your messages without having to give private information to anyone.



<p align="center">
  <img src="screenshots\screenshot.PNG" alt="image" width="300">
</p>

## Requirements
Calliope requires Ubuntu with CUDA and Docker.

I don't know if it works on Windows, let me know if you try.

## Get the token from BotFather

You can get your token from BotFather following [this guide](https://core.telegram.org/bots/tutorial#obtain-your-bot-token).

Then copy the .env.example with 
```
cp .env.example .env
```
and replace the token in .env file with your token.

## Starting Calliope
You can start Calliope with

    docker compose up

## Usage
You can forward any voice or video message to your bot runnig Calliope or you can add your bot to a group for automatically convert any voice or video message to a text.

## Database backup and restore
You can back up the MongoDB database to a single compressed file with

    ./scripts/backup_db.sh

The backup is saved in the `backups/` folder. To restore it (existing collections are overwritten):

    ./scripts/restore_db.sh backups/<backup-file>.archive.gz

Both scripts require the MongoDB container to be running (`docker compose up -d mongodb`).

To move Calliope to another machine: run the backup script on the old machine, copy the backup file to the new one, start MongoDB there with `docker compose up -d mongodb`, then run the restore script with the copied file.
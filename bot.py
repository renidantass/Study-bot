import discord
import datetime
import sqlite3
import os
from dotenv import load_dotenv


load_dotenv()


BOT_NAME = 'Study bot'
DESIRED_CHANNEL_NAME = 'Estudando'
VOICE_CHANNEL = {}


timings = {}


def create_database():
    conn = sqlite3.connect('timings.db')
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS historico (id INTEGER PRIMARY KEY, usuario TEXT, dia DATE, horas INTEGER, minutos INTEGER, segundos INTEGER)')
    cursor.execute('CREATE TABLE IF NOT EXISTS alertas (id INTEGER PRIMARY KEY, usuario TEXT, dia DATE, descricao TEXT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS config (id INTEGER PRIMARY KEY, usuario TEXT, chave TEXT, valor TEXT)')
    conn.commit()
    conn.close()

def upsert_config(user, key, value):
    conn = sqlite3.connect('timings.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM config WHERE usuario = ? AND chave = ?', (user, key))
    if cursor.fetchone() is None:
        cursor.execute('INSERT INTO config (usuario, chave, valor) VALUES (?, ?, ?)', (user, key, value))
    else:
        cursor.execute('UPDATE config SET valor = ? WHERE usuario = ? AND chave = ?', (value, user, key))
    conn.commit()
    conn.close()

def get_config(user, key):
    conn = sqlite3.connect('timings.db')
    cursor = conn.cursor()
    cursor.execute('SELECT valor FROM config WHERE usuario = ? AND chave = ?', (user, key))
    return cursor.fetchone()

def insert_timing(user, horas, minutos, segundos):
    conn = sqlite3.connect('timings.db')
    cursor = conn.cursor()
    cursor.execute('INSERT INTO historico (usuario, dia, horas, minutos, segundos) VALUES (?, DATE(), ?, ?, ?)', (user, horas, minutos, segundos))
    conn.commit()
    conn.close()

def insert_warning(user, description):
    conn = sqlite3.connect('timings.db')
    cursor = conn.cursor()
    cursor.execute('INSERT INTO alertas (usuario, dia, descricao) VALUES (?, DATE(), ?)', (user, description))
    conn.commit()
    conn.close()

def get_all_timings_from_user(user):
    conn = sqlite3.connect('timings.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM historico WHERE usuario = ?', (user,))
    conn.close()

def get_all_users():
    conn = sqlite3.connect('timings.db')
    cursor = conn.cursor()
    resp = cursor.execute('SELECT DISTINCT usuario FROM historico')
    return resp

def get_time_on_day(user):
    conn = sqlite3.connect('timings.db')
    cursor = conn.cursor()
    resp = cursor.execute("""
    SELECT
  FLOOR(total_seconds / 3600) AS horas,
  FLOOR((total_seconds % 3600) / 60) AS minutos,
  (total_seconds % 3600) % 60 AS segundos
FROM (
  SELECT
    SUM(horas) * 3600 + SUM(minutos) * 60 + SUM(segundos) AS total_seconds
  FROM historico
  WHERE
    usuario = ?
    AND dia = DATE()
) AS tempo_total;
    """, (user,))
    return resp

def get_all_timings_on_a_day():
    users = get_all_users()
    for user in users:
        timing = get_time_on_day(user[0])
        hours, minutes, seconds = timing.fetchone()
        print(f'{user[0]} estudou {hours} hora(s), {minutes} minuto(s) e {seconds} segundo(s) hoje')

def calculate(a, b, raw_response=False):
    diff = b - a
    print(diff)
    print(diff.total_seconds())
    
    hours, rest = divmod(diff.total_seconds(), 3600)
    minutes, seconds = divmod(rest, 60)
    
    hours = int(hours)
    minutes = int(minutes)
    seconds = int(seconds)

    dt = datetime.datetime.now()

    if raw_response:
        return hours, minutes, seconds

    return f"{hours:02d} horas, {minutes:02d} minutos e {seconds:02d} segundos estudando hoje ({dt.day}/{dt.month}/{dt.year})"
   
class MyClient(discord.Client):
    async def on_ready(self):
        create_database()

        guild = client.guilds[0]
        voice_channels = [channel for channel in guild.channels if isinstance(channel, discord.VoiceChannel)]
        desired_channel = [ch for ch in voice_channels if ch.name == DESIRED_CHANNEL_NAME][0]

        voice = self.get_channel(desired_channel.id)
        await voice.connect()

    async def on_message(self, message):
        if message.content.startswith('\\estudo'):
            args = message.content.split(' ')
            if len(args) < 2:
                await message.channel.send('Você precisa especificar um tempo de estudo.')
                return

            study_time = args[2]
            upsert_config(message.author.name, 'study_time', study_time)
        else:
            print(f'Mensagem de {message.author}: {message.content}')

    async def on_voice_state_update(self, member, before, after):
        if before.channel is not None:
            if before.channel.name == DESIRED_CHANNEL_NAME:
                if member.name not in timings or member.name == BOT_NAME:
                    return

                print(f"{member.name} saiu do canal de voz.")
                timings[member.name]['saiu'] = datetime.datetime.now()
                calculed = calculate(timings[member.name]['entrou'], timings[member.name]['saiu'])
                channel_in_use = self.voice_clients[0]
                await channel_in_use.channel.send(f'{member.name} ficou {calculed}')

                hours, minutes, seconds = calculate(timings[member.name]['entrou'], timings[member.name]['saiu'], raw_response=True)
                insert_timing(member.name, hours, minutes, seconds)

                minimum_study_time = get_config(member.name, 'study_time')[0]

                hours_on_day = get_time_on_day(member.name).fetchone()[0]

                if hours_on_day < int(minimum_study_time):
                    insert_warning(member.name, f'{member.name} estudou menos de {minimum_study_time} horas')
                    await channel_in_use.channel.send(f'{member.name} estudou menos de {minimum_study_time} horas')

        if after.channel is not None:
            if after.channel.name == DESIRED_CHANNEL_NAME:
                print(f"{member.name} entrou no canal de voz.")
                timings[member.name] = { 'entrou': datetime.datetime.now() }

                if member.name != BOT_NAME:
                    channel_in_use = self.voice_clients[0]
                    await channel_in_use.channel.send(f'{member.name} começou a estudar!')

intents = discord.Intents.default()
intents.message_content = True

client = MyClient(intents=intents)

token = os.getenv('DISCORD_TOKEN', '')

if token == '':
    raise Exception('Token não encontrado')

client.run(token)

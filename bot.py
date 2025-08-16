import discord
from discord.ext import commands
import random
import threading
from flask import Flask, request
import requests
import os
import json
import base64
import re

# ======================
# SPOTIFY CONFIG
# ======================
CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")

# IMPORTANT: Manually set your public Render URL here.
# This is the definitive fix for the "Invalid redirect URI" error.
# Example: "https://my-cool-bot.onrender.com/callback"
REDIRECT_URI = "https://spotify-discord-bot-92vw.onrender.com/callback"


TOKEN_FILE = "spotify_tokens.json"

access_token = None
refresh_token = None

# ======================
# TOKEN HELPER FUNCTIONS
# ======================

def save_tokens(token_data):
    """Saves access and refresh tokens to a file."""
    global access_token, refresh_token
    access_token = token_data.get("access_token")
    # Refresh token might not always be sent, so only update if it exists
    if "refresh_token" in token_data:
        refresh_token = token_data.get("refresh_token")

    # Save the current valid tokens
    with open(TOKEN_FILE, "w") as f:
        json.dump({
            "access_token": access_token,
            "refresh_token": refresh_token
        }, f)

def load_tokens():
    """Loads tokens from a file if it exists."""
    global access_token, refresh_token
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "r") as f:
            data = json.load(f)
            access_token = data.get("access_token")
            refresh_token = data.get("refresh_token")
            return True
    return False

def refresh_spotify_token():
    """Uses the refresh token to get a new access token."""
    if not refresh_token:
        return False

    print("Attempting to refresh Spotify token...")
    token_url = "https://accounts.spotify.com/api/token"

    # Correctly encode client_id:client_secret for the Authorization header
    auth_string = f"{CLIENT_ID}:{CLIENT_SECRET}"
    auth_bytes = auth_string.encode("utf-8")
    auth_base64 = base64.b64encode(auth_bytes).decode("utf-8")

    headers = {
        "Authorization": f"Basic {auth_base64}",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token
    }

    response = requests.post(token_url, headers=headers, data=data)

    if response.status_code == 200:
        new_token_data = response.json()
        save_tokens(new_token_data)
        print("✅ Spotify token refreshed successfully.")
        return True
    else:
        print(f"❌ Failed to refresh Spotify token: {response.text}")
        return False

# Flask app for OAuth
flask_app = Flask(__name__)

@flask_app.route("/callback")
def callback():
    code = request.args.get("code")
    if not code:
        return "No code found in URL."

    # Exchange code for token
    token_url = "https://accounts.spotify.com/api/token"
    response = requests.post(token_url, data={
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET
    })

    if response.status_code == 200:
        token_data = response.json()
        save_tokens(token_data)
        return f"✅ Spotify authorized! You can return to Discord now.<br>Access Token: {access_token[:40]}..."
    else:
        return f"Error authorizing: {response.text}"

def run_flask():
    # Use the PORT provided by the hosting service
    port = int(os.environ.get('PORT', 8080))
    flask_app.run(host='0.0.0.0', port=port)

# ======================
# DISCORD BOT
# ======================
intents = discord.Intents.default()
intents.message_content = True
intents.presences = True
intents.members = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)
bot.is_spotify_ready = False

# Remove the default help command
bot.remove_command('help')

last_song = {}

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    if not bot.is_spotify_ready:
        if load_tokens():
            if refresh_spotify_token():
                bot.is_spotify_ready = True
        else:
            print("No Spotify tokens found. Use !spotify_login to authorize.")


@bot.command()
async def hello(ctx):
    await ctx.send("Hello! I am alive😎")

@bot.command()
async def roll(ctx):
    await ctx.send(f"🎲 You rolled a **{random.randint(1, 6)}**!")

# New command: Custom Help Command
@bot.command()
async def help(ctx):
    embed = discord.Embed(
        title="HarmoNeko Bot Commands",
        description="Here are all the available commands:",
        color=0x1DB954
    )
    embed.set_thumbnail(url=bot.user.avatar.url)

    embed.add_field(
        name="🤖 General Commands",
        value="`!hello` - Check if the bot is alive.\n"
              "`!roll` - Roll a six-sided die.",
        inline=False
    )

    embed.add_field(
        name="🎵 Spotify Setup",
        value="`!spotify_login` - Authorize your Spotify account.\n"
              "`!spotify_token` - Check the status of your token.",
        inline=False
    )

    embed.add_field(
        name="⏯️ Spotify Playback Controls",
        value="`!play [song name]` - Play a song or resume playback.\n"
              "`!spotify_pause` - Pause the current song.\n"
              "`!spotify_next` - Skip to the next song.\n"
              "`!spotify_previous` - Go to the previous song.\n"
              "`!spotify_volume [0-100]` - Set the playback volume.",
        inline=False
    )

    embed.add_field(
        name="✨ Spotify Features",
        value="`!queue [song name]` - Add a song to your queue.\n"
              "`!save` - Save the current song to your Liked Songs.\n"
              "`!nowplaying` or `!np` - Show the currently playing song.\n"
              "`!recommend` - Get song recommendations.\n"
              "`!lyrics` - Get lyrics for the current song.",
        inline=False
    )

    embed.set_footer(text="Remember to run !spotify_login first!")
    await ctx.send(embed=embed)


# ======================
# SPOTIFY COMMANDS
# ======================

@bot.command()
async def spotify_login(ctx):
    # Added new scopes for queueing, saving songs, and recommendations
    scopes = [
        "user-modify-playback-state",
        "user-read-playback-state",
        "user-read-currently-playing",
        "user-library-modify",
        "user-top-read"
    ]
    scope_str = "%20".join(scopes)

    auth_url = (
        f"https://accounts.spotify.com/authorize"
        f"?client_id={CLIENT_ID}"
        f"&response_type=code"
        f"&redirect_uri={REDIRECT_URI}"
        f"&scope={scope_str}"
    )
    await ctx.send(f"Click here to authorize Spotify:\n{auth_url}")

@bot.command()
async def spotify_token(ctx):
    if access_token:
        await ctx.send(f"✅ Current Spotify access token starts with: `{access_token[:25]}...`")
    else:
        await ctx.send("❌ No Spotify access token yet. Use `!spotify_login` first.")

# Helper function for handling Spotify API errors
async def handle_spotify_error(ctx, response):
    """Parses Spotify API errors and sends a user-friendly message."""
    if response.status_code == 401:
        await ctx.send("⚠️ Your Spotify token has expired. Please use `!spotify_login` again.")
        return

    try:
        error_data = response.json()
        reason = error_data.get("error", {}).get("reason")

        if reason == "PREMIUM_REQUIRED":
            await ctx.send("❌ This command requires a Spotify Premium account.")
            return

        if reason == "NO_ACTIVE_DEVICE":
            await ctx.send("❌ No active Spotify device found! Please start playing music on a device.")
            return

        # Fallback for other JSON errors
        error_message = error_data.get("error", {}).get("message", "An unknown error occurred.")
        await ctx.send(f"⚠️ Spotify API Error: {error_message}")

    except json.JSONDecodeError:
        # This handles cases where the API response isn't JSON
        if response.status_code == 403 or response.status_code == 404:
            await ctx.send("❌ No active Spotify device found! Please start playing music on a device.")
        else:
            # For any other unknown error, do not send a message to the chat.
            # Just print it to the console for debugging.
            print(f"An unhandled Spotify API error occurred: {response.status_code} - {response.text}")
            pass


# Pause playback
@bot.command()
async def spotify_pause(ctx):
    if not access_token:
        await ctx.send("❌ No Spotify token. Use `!spotify_login` first.")
        return

    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.put("https://api.spotify.com/v1/me/player/pause", headers=headers)

    if response.status_code == 204:
        await ctx.send("⏸️ Song paused!")
    else:
        await handle_spotify_error(ctx, response)

# Resume playback or play a specific song
@bot.command()
async def play(ctx, *, song_query: str = None):
    if not access_token:
        await ctx.send("❌ No Spotify token. Use `!spotify_login` first.")
        return

    headers = {"Authorization": f"Bearer {access_token}"}

    # If no song is provided, just resume playback
    if song_query is None:
        response = requests.put("https://api.spotify.com/v1/me/player/play", headers=headers)
        if response.status_code == 204:
            await ctx.send("▶️ Resumed playback!")
        else:
            await handle_spotify_error(ctx, response)
        return

    # If a song is provided, search for it and play it
    search_url = f"https://api.spotify.com/v1/search?q={song_query}&type=track&limit=1"
    response = requests.get(search_url, headers=headers)

    if response.status_code != 200:
        await ctx.send("⚠️ Could not search for the song.")
        return

    results = response.json()
    tracks = results.get("tracks", {}).get("items", [])

    if not tracks:
        await ctx.send(f"❌ Could not find a song matching `{song_query}`.")
        return

    track_uri = tracks[0]["uri"]
    track_name = tracks[0]["name"]

    play_data = json.dumps({"uris": [track_uri]})
    play_response = requests.put("https://api.spotify.com/v1/me/player/play", headers=headers, data=play_data)

    if play_response.status_code == 204:
        await ctx.send(f"▶️ Now playing: **{track_name}**")
    else:
        await handle_spotify_error(ctx, play_response)


# Next track
@bot.command()
async def spotify_next(ctx):
    if not access_token:
        await ctx.send("❌ No Spotify token. Use `!spotify_login` first.")
        return

    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.post("https://api.spotify.com/v1/me/player/next", headers=headers)

    if response.status_code == 204:
        await ctx.send("⏭️ Skipped to next track!")
    else:
        await handle_spotify_error(ctx, response)


# Previous track
@bot.command()
async def spotify_previous(ctx):
    if not access_token:
        await ctx.send("❌ No Spotify token. Use `!spotify_login` first.")
        return

    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.post("https://api.spotify.com/v1/me/player/previous", headers=headers)

    if response.status_code == 204:
        await ctx.send("⏮️ Went back to previous track!")
    else:
        await handle_spotify_error(ctx, response)

# Set volume (0-100)
@bot.command()
async def spotify_volume(ctx, volume: int):
    if not access_token:
        await ctx.send("❌ No Spotify token. Use `!spotify_login` first.")
        return

    if not (0 <= volume <= 100):
        await ctx.send("⚠️ Volume must be between 0 and 100.")
        return

    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.put(f"https://api.spotify.com/v1/me/player/volume?volume_percent={volume}", headers=headers)

    if response.status_code == 204:
        await ctx.send(f"🔊 Volume set to {volume}%")
    else:
        await handle_spotify_error(ctx, response)

# Queue a song
@bot.command()
async def queue(ctx, *, song_query: str):
    """Searches for a song and adds it to the Spotify queue."""
    if not access_token:
        await ctx.send("❌ No Spotify token. Use `!spotify_login` first.")
        return

    headers = {"Authorization": f"Bearer {access_token}"}
    search_url = f"https://api.spotify.com/v1/search?q={song_query}&type=track&limit=1"

    response = requests.get(search_url, headers=headers)
    if response.status_code != 200:
        await ctx.send("⚠️ Could not search for the song.")
        return

    results = response.json()
    tracks = results.get("tracks", {}).get("items", [])

    if not tracks:
        await ctx.send(f"❌ Could not find a song matching `{song_query}`.")
        return

    track_uri = tracks[0]["uri"]
    track_name = tracks[0]["name"]

    queue_url = f"https://api.spotify.com/v1/me/player/queue?uri={track_uri}"
    queue_response = requests.post(queue_url, headers=headers)

    if queue_response.status_code == 204:
        await ctx.send(f"✅ Added **{track_name}** to the queue.")
    else:
        await handle_spotify_error(ctx, queue_response)

# Show currently playing song
@bot.command(aliases=['np'])
async def nowplaying(ctx):
    """Shows details about the currently playing song."""
    if not access_token:
        await ctx.send("❌ No Spotify token. Use `!spotify_login` first.")
        return

    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get("https://api.spotify.com/v1/me/player/currently-playing", headers=headers)

    if response.status_code == 204:
        await ctx.send("Nothing is currently playing.")
        return
    if response.status_code != 200:
        await handle_spotify_error(ctx, response)
        return

    data = response.json()
    item = data.get('item')
    if not item:
        await ctx.send("Nothing is currently playing.")
        return

    embed = discord.Embed(
        title=item['name'],
        description=f"by *{', '.join([artist['name'] for artist in item['artists']])}*",
        color=0x1DB954
    )
    embed.add_field(name="Album", value=item['album']['name'], inline=False)
    embed.set_thumbnail(url=item['album']['images'][0]['url'])
    await ctx.send(embed=embed)

# Save the current song
@bot.command()
async def save(ctx):
    """Saves the currently playing song to your Liked Songs."""
    if not access_token:
        await ctx.send("❌ No Spotify token. Use `!spotify_login` first.")
        return

    headers = {"Authorization": f"Bearer {access_token}"}
    # First, get the current song
    current_song_response = requests.get("https://api.spotify.com/v1/me/player/currently-playing", headers=headers)

    if current_song_response.status_code != 200:
        await ctx.send("⚠️ Could not get the currently playing song.")
        return

    data = current_song_response.json()
    item = data.get('item')
    if not item:
        await ctx.send("Nothing is currently playing to save.")
        return

    track_id = item['id']
    track_name = item['name']

    # Now, save the song
    save_url = f"https://api.spotify.com/v1/me/tracks?ids={track_id}"
    save_response = requests.put(save_url, headers=headers)

    if save_response.status_code == 200:
        await ctx.send(f"✅ Saved **{track_name}** to your Liked Songs.")
    else:
        await handle_spotify_error(ctx, save_response)

# New command: Get song recommendations
@bot.command()
async def recommend(ctx):
    """Recommends songs based on the currently playing track."""
    if not access_token:
        await ctx.send("❌ No Spotify token. Use `!spotify_login` first.")
        return

    headers = {"Authorization": f"Bearer {access_token}"}
    # First, get the current song to use as a seed
    current_song_response = requests.get("https://api.spotify.com/v1/me/player/currently-playing", headers=headers)

    if current_song_response.status_code != 200:
        await ctx.send("⚠️ Could not get the currently playing song to base recommendations on.")
        return

    data = current_song_response.json()
    item = data.get('item')
    if not item:
        await ctx.send("Nothing is currently playing to base recommendations on.")
        return

    seed_track_id = item['id']

    # Get recommendations
    rec_url = f"https://api.spotify.com/v1/recommendations?limit=5&seed_tracks={seed_track_id}"
    rec_response = requests.get(rec_url, headers=headers)

    if rec_response.status_code != 200:
        await handle_spotify_error(ctx, rec_response)
        return

    rec_data = rec_response.json()
    tracks = rec_data.get('tracks', [])

    if not tracks:
        await ctx.send("Could not find any recommendations.")
        return

    embed = discord.Embed(
        title=f"Recommendations based on {item['name']}",
        color=0x1DB954
    )
    for track in tracks:
        track_name = track['name']
        artists = ", ".join([artist['name'] for artist in track['artists']])
        embed.add_field(name=track_name, value=f"by *{artists}*", inline=False)

    await ctx.send(embed=embed)

# New command: Get lyrics
@bot.command()
async def lyrics(ctx):
    """Gets lyrics for the currently playing song."""
    if not access_token:
        await ctx.send("❌ No Spotify token. Use `!spotify_login` first.")
        return

    headers = {"Authorization": f"Bearer {access_token}"}
    # First, get the current song
    current_song_response = requests.get("https://api.spotify.com/v1/me/player/currently-playing", headers=headers)

    if current_song_response.status_code != 200:
        await ctx.send("⚠️ Could not get the currently playing song.")
        return

    data = current_song_response.json()
    item = data.get('item')
    if not item:
        await ctx.send("Nothing is currently playing.")
        return

    # Clean up artist and title for a better search
    artist = item['artists'][0]['name']
    title = item['name']
    # Remove extra info like "(feat. ...)" for a better match
    title_cleaned = re.sub(r'\(.+\)', '', title).strip()

    await ctx.send(f"Searching for lyrics for **{title}**...")

    # Fetch lyrics from lyrics.ovh API
    lyrics_url = f"https://api.lyrics.ovh/v1/{artist}/{title_cleaned}"
    lyrics_response = requests.get(lyrics_url)

    if lyrics_response.status_code == 200:
        lyrics_data = lyrics_response.json()
        song_lyrics = lyrics_data.get('lyrics')

        if not song_lyrics:
            await ctx.send(f"❌ Could not find lyrics for **{title}**.")
            return

        # Discord has a 2000 character limit per message
        if len(song_lyrics) > 2000:
            # Send in chunks
            embed = discord.Embed(title=f"Lyrics for {title} by {artist}", description=song_lyrics[:2000], color=0x1DB954)
            await ctx.send(embed=embed)
            for i in range(2000, len(song_lyrics), 2000):
                await ctx.send(song_lyrics[i:i+2000])
        else:
            embed = discord.Embed(title=f"Lyrics for {title} by {artist}", description=song_lyrics, color=0x1DB954)
            await ctx.send(embed=embed)
    else:
        await ctx.send(f"❌ Could not find lyrics for **{title}**.")

# ======================
# PRESENCE LISTENER
# ======================
@bot.event
async def on_presence_update(before, after):
    if after.bot:
        return

    before_spotify = discord.utils.find(lambda a: isinstance(a, discord.Spotify), before.activities)
    after_spotify = discord.utils.find(lambda a: isinstance(a, discord.Spotify), after.activities)

    if after_spotify is not None:
        user_id = after.id
        current_song = (after_spotify.title, tuple(after_spotify.artists))

        if last_song.get(user_id) != current_song:
            last_song[user_id] = current_song

            channel = discord.utils.get(after.guild.text_channels, name="general")
            if not channel:
                return

            embed = discord.Embed(
                title=f"{after.display_name} is vibing 🎶",
                description=f"**{after.spotify.title}**\nby *{', '.join(after.spotify.artists)}*",
                color=0x1DB954
            )
            embed.add_field(name="Album", value=after.spotify.album, inline=False)
            embed.set_thumbnail(url=after.spotify.album_cover_url)
            embed.set_footer(text="Powered by Spotify 🎧")

            await channel.send(embed=embed)

# ======================
# START EVERYTHING
# ======================
if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()  # run Flask in background

    bot_token = os.getenv("DISCORD_BOT_TOKEN")
    bot.run(bot_token)

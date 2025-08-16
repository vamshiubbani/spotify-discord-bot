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
import uuid

# ======================
# SPOTIFY CONFIG
# ======================
CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")

# IMPORTANT: Manually set your public Render URL here.
REDIRECT_URI = "https://spotify-discord-bot-lmhu.onrender.com/callback"


TOKEN_FILE = "spotify_tokens.json"

# This dictionary will temporarily store a user's ID while they log in
pending_oauth_states = {}

# ======================
# TOKEN HELPER FUNCTIONS (NOW MULTI-USER)
# ======================

def load_all_tokens():
    """Loads all user tokens from the JSON file."""
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "r") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}

def save_all_tokens(tokens):
    """Saves all user tokens to the JSON file."""
    with open(TOKEN_FILE, "w") as f:
        json.dump(tokens, f, indent=4)

def get_user_tokens(user_id):
    """Gets tokens for a specific user."""
    all_tokens = load_all_tokens()
    return all_tokens.get(str(user_id))

def save_user_tokens(user_id, token_data):
    """Saves tokens for a specific user."""
    all_tokens = load_all_tokens()
    
    current_tokens = all_tokens.get(str(user_id), {})
    current_tokens["access_token"] = token_data.get("access_token")
    # Only update the refresh token if a new one is provided
    if "refresh_token" in token_data:
        current_tokens["refresh_token"] = token_data.get("refresh_token")
        
    all_tokens[str(user_id)] = current_tokens
    save_all_tokens(all_tokens)

def refresh_spotify_token(user_id):
    """Uses a user's refresh token to get a new access token."""
    user_tokens = get_user_tokens(user_id)
    if not user_tokens or "refresh_token" not in user_tokens:
        return None

    print(f"Attempting to refresh Spotify token for user {user_id}...")
    token_url = "https://accounts.spotify.com/api/token"
    
    auth_string = f"{CLIENT_ID}:{CLIENT_SECRET}"
    auth_bytes = auth_string.encode("utf-8")
    auth_base64 = base64.b64encode(auth_bytes).decode("utf-8")

    headers = {
        "Authorization": f"Basic {auth_base64}",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    data = {
        "grant_type": "refresh_token",
        "refresh_token": user_tokens["refresh_token"]
    }
    
    response = requests.post(token_url, headers=headers, data=data)
    
    if response.status_code == 200:
        new_token_data = response.json()
        save_user_tokens(user_id, new_token_data)
        print(f"✅ Spotify token refreshed successfully for user {user_id}.")
        return new_token_data.get("access_token")
    else:
        print(f"❌ Failed to refresh Spotify token for user {user_id}: {response.text}")
        # If refresh fails, remove the invalid tokens
        all_tokens = load_all_tokens()
        all_tokens.pop(str(user_id), None)
        save_all_tokens(all_tokens)
        return None

# Flask app for OAuth
flask_app = Flask(__name__)

@flask_app.route("/callback")
def callback():
    code = request.args.get("code")
    state = request.args.get("state")

    if not code or not state:
        return "Error: Missing code or state from Spotify callback."

    user_id = pending_oauth_states.pop(state, None)
    if not user_id:
        return "Error: Invalid or expired state. Please try logging in again."

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
        save_user_tokens(user_id, token_data)
        return "✅ Spotify authorized! You can return to Discord now."
    else:
        return f"Error authorizing: {response.text}"

def run_flask():
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
bot.remove_command('help')
last_song = {}

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")

# This is a decorator that checks if a user is logged in before running a command
def spotify_login_required():
    async def predicate(ctx):
        if get_user_tokens(ctx.author.id) is None:
            await ctx.send("❌ You need to log in with Spotify first! Use `!spotify_login`.")
            return False
        return True
    return commands.check(predicate)

async def spotify_api_request(user_id, method, url, json_data=None, data=None):
    """A helper function to make authenticated Spotify API requests for a user."""
    tokens = get_user_tokens(user_id)
    if not tokens:
        return None, "User not logged in"

    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    
    # Make the initial request
    response = requests.request(method, url, headers=headers, json=json_data, data=data)

    # If token is expired, refresh it and try again
    if response.status_code == 401:
        new_access_token = refresh_spotify_token(user_id)
        if new_access_token:
            headers["Authorization"] = f"Bearer {new_access_token}"
            response = requests.request(method, url, headers=headers, json=json_data, data=data)
    
    return response, None

@bot.command()
async def hello(ctx):
    await ctx.send("Hello! I am alive😎")

@bot.command()
async def roll(ctx):
    await ctx.send(f"🎲 You rolled a **{random.randint(1, 6)}**!")

@bot.command()
async def help(ctx):
    embed = discord.Embed(
        title="HarmoNeko Bot Commands",
        description="Here are all the available commands:",
        color=0x1DB954
    )
    embed.set_thumbnail(url=bot.user.avatar.url)
    embed.add_field(name="🎵 Spotify Setup", value="`!spotify_login` - Authorize your Spotify account.", inline=False)
    embed.add_field(name="⏯️ Spotify Playback Controls", value="`!play [song name]` - Play a song or resume playback.\n`!spotify_pause` - Pause the current song.\n`!spotify_next` - Skip to the next song.\n`!spotify_previous` - Go to the previous song.\n`!spotify_volume [0-100]` - Set the playback volume.", inline=False)
    embed.add_field(name="✨ Spotify Features", value="`!queue [song name]` - Add a song to your queue.\n`!save` - Save the current song to your Liked Songs.\n`!nowplaying` or `!np` - Show the currently playing song.\n`!recommend` - Get song recommendations.\n`!lyrics` - Get lyrics for the current song.", inline=False)
    embed.set_footer(text="Anyone can use these commands after logging in!")
    await ctx.send(embed=embed)


# ======================
# SPOTIFY COMMANDS
# ======================

@bot.command()
async def spotify_login(ctx):
    state = str(uuid.uuid4())
    pending_oauth_states[state] = ctx.author.id

    scopes = ["user-modify-playback-state", "user-read-playback-state", "user-read-currently-playing", "user-library-modify", "user-top-read"]
    scope_str = "%20".join(scopes)
    
    auth_url = (f"https://accounts.spotify.com/authorize?client_id={CLIENT_ID}&response_type=code"
                f"&redirect_uri={REDIRECT_URI}&scope={scope_str}&state={state}")
    
    try:
        await ctx.author.send(f"Click here to authorize your Spotify account:\n{auth_url}")
        await ctx.send("✅ I've sent you a private message with the login link.")
    except discord.Forbidden:
        await ctx.send("⚠️ I couldn't send you a private message. Please check your privacy settings.")

async def handle_spotify_error(ctx, response):
    """Parses Spotify API errors and sends a user-friendly message."""
    if response is None:
        return
        
    if response.status_code == 401:
        await ctx.send("⚠️ Your Spotify token has expired or is invalid. Please use `!spotify_login` again.")
        return

    try:
        error_data = response.json()
        reason = error_data.get("error", {}).get("reason")
        
        if reason == "PREMIUM_REQUIRED":
            await ctx.send("❌ This command requires a Spotify Premium account.")
        elif reason == "NO_ACTIVE_DEVICE":
            await ctx.send("❌ No active Spotify device found! Please start playing music on a device.")
        else:
            error_message = error_data.get("error", {}).get("message", "An unknown error occurred.")
            await ctx.send(f"⚠️ Spotify API Error: {error_message}")

    except json.JSONDecodeError:
        if response.status_code in [403, 404]:
            await ctx.send("❌ No active Spotify device found! Please start playing music on a device.")
        else:
            print(f"An unhandled Spotify API error occurred: {response.status_code} - {response.text}")

@bot.command()
@spotify_login_required()
async def play(ctx, *, song_query: str = None):
    user_id = ctx.author.id
    if song_query is None:
        response, err = await spotify_api_request(user_id, 'put', "https://api.spotify.com/v1/me/player/play")
        if response and response.status_code == 204:
            await ctx.send("▶️ Resumed playback!")
        else:
            await handle_spotify_error(ctx, response)
        return

    search_url = f"https://api.spotify.com/v1/search?q={song_query}&type=track&limit=1"
    response, err = await spotify_api_request(user_id, 'get', search_url)
    
    if not response or response.status_code != 200:
        await ctx.send("⚠️ Could not search for the song.")
        return
        
    results = response.json()
    tracks = results.get("tracks", {}).get("items", [])
    if not tracks:
        await ctx.send(f"❌ Could not find a song matching `{song_query}`.")
        return

    track_uri = tracks[0]["uri"]
    track_name = tracks[0]["name"]
    
    play_response, err = await spotify_api_request(user_id, 'put', "https://api.spotify.com/v1/me/player/play", json_data={"uris": [track_uri]})
    if play_response and play_response.status_code == 204:
        await ctx.send(f"▶️ Now playing: **{track_name}**")
    else:
        await handle_spotify_error(ctx, play_response)

@bot.command()
@spotify_login_required()
async def spotify_pause(ctx):
    response, err = await spotify_api_request(ctx.author.id, 'put', "https://api.spotify.com/v1/me/player/pause")
    if response and response.status_code == 204:
        await ctx.send("⏸️ Song paused!")
    else:
        await handle_spotify_error(ctx, response)

@bot.command()
@spotify_login_required()
async def spotify_next(ctx):
    response, err = await spotify_api_request(ctx.author.id, 'post', "https://api.spotify.com/v1/me/player/next")
    if response and response.status_code == 204:
        await ctx.send("⏭️ Skipped to next track!")
    else:
        await handle_spotify_error(ctx, response)

@bot.command()
@spotify_login_required()
async def spotify_previous(ctx):
    response, err = await spotify_api_request(ctx.author.id, 'post', "https://api.spotify.com/v1/me/player/previous")
    if response and response.status_code == 204:
        await ctx.send("⏮️ Went back to previous track!")
    else:
        await handle_spotify_error(ctx, response)

@bot.command()
@spotify_login_required()
async def spotify_volume(ctx, volume: int):
    if not (0 <= volume <= 100):
        await ctx.send("⚠️ Volume must be between 0 and 100.")
        return
    url = f"https://api.spotify.com/v1/me/player/volume?volume_percent={volume}"
    response, err = await spotify_api_request(ctx.author.id, 'put', url)
    if response and response.status_code == 204:
        await ctx.send(f"🔊 Volume set to {volume}%")
    else:
        await handle_spotify_error(ctx, response)

@bot.command()
@spotify_login_required()
async def queue(ctx, *, song_query: str):
    user_id = ctx.author.id
    search_url = f"https://api.spotify.com/v1/search?q={song_query}&type=track&limit=1"
    response, err = await spotify_api_request(user_id, 'get', search_url)
    if not response or response.status_code != 200:
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
    queue_response, err = await spotify_api_request(user_id, 'post', queue_url)
    if queue_response and queue_response.status_code == 204:
        await ctx.send(f"✅ Added **{track_name}** to the queue.")
    else:
        await handle_spotify_error(ctx, queue_response)

@bot.command(aliases=['np'])
@spotify_login_required()
async def nowplaying(ctx):
    response, err = await spotify_api_request(ctx.author.id, 'get', "https://api.spotify.com/v1/me/player/currently-playing")
    if not response or response.status_code != 200:
        await ctx.send("Nothing is currently playing.")
        return

    data = response.json()
    item = data.get('item')
    if not item:
        await ctx.send("Nothing is currently playing.")
        return

    embed = discord.Embed(title=item['name'], description=f"by *{', '.join([artist['name'] for artist in item['artists']])}*", color=0x1DB954)
    embed.add_field(name="Album", value=item['album']['name'], inline=False)
    embed.set_thumbnail(url=item['album']['images'][0]['url'])
    await ctx.send(embed=embed)

@bot.command()
@spotify_login_required()
async def save(ctx):
    user_id = ctx.author.id
    response, err = await spotify_api_request(user_id, 'get', "https://api.spotify.com/v1/me/player/currently-playing")
    if not response or response.status_code != 200:
        await ctx.send("⚠️ Could not get the currently playing song.")
        return

    data = response.json()
    item = data.get('item')
    if not item:
        await ctx.send("Nothing is currently playing to save.")
        return
    
    track_id = item['id']
    track_name = item['name']

    save_url = f"https://api.spotify.com/v1/me/tracks?ids={track_id}"
    save_response, err = await spotify_api_request(user_id, 'put', save_url, json_data={"ids": [track_id]})
    if save_response and save_response.status_code == 200:
        await ctx.send(f"✅ Saved **{track_name}** to your Liked Songs.")
    else:
        await handle_spotify_error(ctx, save_response)

@bot.command()
@spotify_login_required()
async def recommend(ctx):
    user_id = ctx.author.id
    response, err = await spotify_api_request(user_id, 'get', "https://api.spotify.com/v1/me/player/currently-playing")
    if not response or response.status_code != 200:
        await ctx.send("⚠️ Could not get the currently playing song to base recommendations on.")
        return

    data = response.json()
    item = data.get('item')
    if not item:
        await ctx.send("Nothing is currently playing to base recommendations on.")
        return

    seed_track_id = item['id']
    rec_url = f"https://api.spotify.com/v1/recommendations?limit=5&seed_tracks={seed_track_id}"
    rec_response, err = await spotify_api_request(user_id, 'get', rec_url)
    if not rec_response or rec_response.status_code != 200:
        await handle_spotify_error(ctx, rec_response)
        return

    rec_data = rec_response.json()
    tracks = rec_data.get('tracks', [])
    if not tracks:
        await ctx.send("Could not find any recommendations.")
        return

    embed = discord.Embed(title=f"Recommendations based on {item['name']}", color=0x1DB954)
    for track in tracks:
        track_name = track['name']
        artists = ", ".join([artist['name'] for artist in track['artists']])
        embed.add_field(name=track_name, value=f"by *{artists}*", inline=False)
    await ctx.send(embed=embed)

@bot.command()
@spotify_login_required()
async def lyrics(ctx):
    response, err = await spotify_api_request(ctx.author.id, 'get', "https://api.spotify.com/v1/me/player/currently-playing")
    if not response or response.status_code != 200:
        await ctx.send("⚠️ Could not get the currently playing song.")
        return

    data = response.json()
    item = data.get('item')
    if not item:
        await ctx.send("Nothing is currently playing.")
        return
        
    artist = item['artists'][0]['name']
    title = item['name']
    title_cleaned = re.sub(r'\(.+\)', '', title).strip()

    await ctx.send(f"Searching for lyrics for **{title}**...")
    lyrics_url = f"https://api.lyrics.ovh/v1/{artist}/{title_cleaned}"
    lyrics_response = requests.get(lyrics_url)
    
    if lyrics_response.status_code == 200:
        lyrics_data = lyrics_response.json()
        song_lyrics = lyrics_data.get('lyrics')
        if not song_lyrics:
            await ctx.send(f"❌ Could not find lyrics for **{title}**.")
            return

        if len(song_lyrics) > 2000:
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

    after_spotify = discord.utils.find(lambda a: isinstance(a, discord.Spotify), after.activities)
    if after_spotify is not None:
        user_id = after.id
        current_song = (after_spotify.title, tuple(after_spotify.artists))
        if last_song.get(user_id) != current_song:
            last_song[user_id] = current_song
            channel = discord.utils.get(after.guild.text_channels, name="general")
            if not channel:
                return

            embed = discord.Embed(title=f"{after.display_name} is vibing 🎶", description=f"**{after_spotify.title}**\nby *{', '.join(after_spotify.artists)}*", color=0x1DB954)
            embed.add_field(name="Album", value=after_spotify.album, inline=False)
            embed.set_thumbnail(url=after_spotify.album_cover_url)
            embed.set_footer(text="Powered by Spotify 🎧")
            await channel.send(embed=embed)

# ======================
# START EVERYTHING
# ======================
if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    bot_token = os.getenv("DISCORD_BOT_TOKEN")
    bot.run(bot_token)


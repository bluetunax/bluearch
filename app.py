from atproto import Client, models, AtUri
import csv
import time
import os
from datetime import datetime
import traceback
import html
import configparser
import requests 
import uuid     
from urllib.parse import urlparse 
# No longer need 'import atproto' just for version for the footer

# --- Configuration ---
CONFIG_FILE = 'config.ini'
ASSETS_FOLDER_NAME = 'assets' # Just the name of the subfolder
# OUTPUT_FILENAME_TEMPLATE_CSV and _HTML will be used for basenames inside the archive folder
OUTPUT_FILENAME_CSV = "archive_data.csv" 
OUTPUT_FILENAME_HTML = "profile_archive.html"
POSTS_PER_REQUEST_LIMIT = 100
REQUEST_DELAY_SECONDS = 1 
IMAGE_DOWNLOAD_DELAY_SECONDS = 0.5 

# --- Helper Functions ---

def load_credentials():
    config = configparser.ConfigParser()
    if not os.path.exists(CONFIG_FILE):
        print(f"Error: Credentials file '{CONFIG_FILE}' not found."); return None, None
    try:
        config.read(CONFIG_FILE)
        handle = config.get('BlueskyCredentials', 'handle')
        app_password = config.get('BlueskyCredentials', 'app_password')
        if not handle or not app_password or handle == "your_login_handle.bsky.social" or app_password == "xxxx-xxxx-xxxx-xxxx":
            print(f"Error: Please update your actual credentials in '{CONFIG_FILE}'."); return None, None
        return handle, app_password
    except Exception as e:
        print(f"Error reading credentials from '{CONFIG_FILE}': {e}"); return None, None

def login_to_bluesky(user_login_handle, app_password):
    client = Client()
    try:
        session_data = client.login(user_login_handle, app_password)
        runner_did = session_data.did; runner_handle = session_data.handle
        profile_params = models.AppBskyActorGetProfile.Params(actor=runner_did)
        profile_details_response = client.app.bsky.actor.get_profile(params=profile_params)
        display_name = profile_details_response.display_name
        if not display_name: display_name = runner_handle 
        print(f"Successfully logged in as script runner: {display_name} (@{runner_handle})")
        print(f"Script runner DID: {runner_did}")
        return client, runner_did, runner_handle
    except Exception as e:
        print(f"Login failed for script runner ({user_login_handle}): {e}"); return None, None, None

def download_image(image_url, assets_dir_full_path_for_saving): # Renamed for clarity
    """Downloads an image and saves it, returning a relative path like 'assets/filename.ext' for HTML."""
    if not image_url: return None
    try:
        original_filename_part = image_url.split('/')[-1].split('@')[0].split('?')[0] 
        file_ext = os.path.splitext(original_filename_part)[1].lower()
        valid_extensions = ['.jpeg', '.jpg', '.png', '.gif', '.webp']
        if file_ext not in valid_extensions or len(file_ext) > 5 : 
            try:
                head_resp = requests.head(image_url, timeout=5, allow_redirects=True)
                head_resp.raise_for_status()
                content_type = head_resp.headers.get('content-type')
                if content_type:
                    if 'jpeg' in content_type or 'jpg' in content_type: file_ext = '.jpg'
                    elif 'png' in content_type: file_ext = '.png'
                    elif 'gif' in content_type: file_ext = '.gif'
                    elif 'webp' in content_type: file_ext = '.webp'
                    else: file_ext = '.jpg' 
                else: file_ext = '.jpg' 
            except requests.exceptions.RequestException: file_ext = '.jpg' 
        unique_id = str(uuid.uuid4().hex[:8]) 
        filename_base = ''.join(c if c.isalnum() or c in ['_','-'] else '' for c in original_filename_part.rsplit('.',1)[0])[:30]
        if not filename_base: filename_base = "image" 
        local_filename_only = f"{filename_base}_{unique_id}{file_ext}"
        local_filepath_full_for_saving = os.path.join(assets_dir_full_path_for_saving, local_filename_only)
        print(f"    Downloading: {image_url} -> {local_filename_only}")
        img_response = requests.get(image_url, stream=True, timeout=20) 
        img_response.raise_for_status()
        with open(local_filepath_full_for_saving, 'wb') as f:
            for chunk in img_response.iter_content(chunk_size=8192): f.write(chunk)
        time.sleep(IMAGE_DOWNLOAD_DELAY_SECONDS) 
        return os.path.join(ASSETS_FOLDER_NAME, local_filename_only) # Crucially, return relative path for HTML
    except requests.exceptions.RequestException as e:
        print(f"    Error downloading {image_url}: {e}"); return None
    except IOError as e:
        print(f"    Error saving image from {image_url}: {e}"); return None
    except Exception as e: 
        print(f"    Unexpected error downloading/saving {image_url}: {e}"); return None

def extract_post_details_for_csv(feed_view_post_item, profile_did_of_archived_user, profile_handle_of_archived_user, assets_dir_full_path):
    # ... (This function remains largely the same, ensuring it uses assets_dir_full_path for download_image)
    post = feed_view_post_item.post 
    record = post.record 
    original_post_author = post.author
    item_type = "post" 
    if isinstance(feed_view_post_item.reason, models.AppBskyFeedDefs.ReasonRepost):
        if feed_view_post_item.reason.by.did == profile_did_of_archived_user: item_type = "repost"
    elif hasattr(record, 'reply') and record.reply and record.reply.parent:
        if original_post_author.did == profile_did_of_archived_user: item_type = "reply"
    author_local_avatar_path = None
    if original_post_author.avatar: 
        print(f"    Fetching avatar for post author @{original_post_author.handle}...")
        author_local_avatar_path = download_image(original_post_author.avatar, assets_dir_full_path)
    details = {
        'profile_user_handle': profile_handle_of_archived_user, 'profile_user_did': profile_did_of_archived_user, 'item_type': item_type,
        'uri': post.uri, 'cid': post.cid, 'author_did': original_post_author.did,
        'author_handle': original_post_author.handle, 'author_display_name': html.escape(original_post_author.display_name or original_post_author.handle),
        'author_local_avatar_path': author_local_avatar_path or '',
        'text': record.text if hasattr(record, 'text') else '',
        'created_at': record.created_at if hasattr(record, 'created_at') else '',
        'langs': ','.join(record.langs) if hasattr(record, 'langs') and record.langs else '',
        'reply_count': post.reply_count if post.reply_count is not None else 0,
        'repost_count': post.repost_count if post.repost_count is not None else 0,
        'like_count': post.like_count if post.like_count is not None else 0,
        'reply_to_post_uri': record.reply.parent.uri if hasattr(record, 'reply') and record.reply and record.reply.parent else '',
        'reply_root_post_uri': record.reply.root.uri if hasattr(record, 'reply') and record.reply and record.reply.root else '',
        'embed_type': '', 'embed_local_image_paths': '', 'embed_image_alts': '',
        'embed_external_url': '', 'embed_external_title': '', 'embed_external_description': '',
        'embed_quote_post_uri': ''
    }
    if isinstance(details['created_at'], datetime): details['created_at'] = details['created_at'].isoformat()
    elif isinstance(record, dict) and 'createdAt' in record: details['created_at'] = record['createdAt']
    if post.embed:
        local_image_paths_list = []
        image_alts_list = []
        if isinstance(post.embed, models.AppBskyEmbedImages.View):
            details['embed_type'] = 'images'
            for img_view in post.embed.images:
                local_path = download_image(img_view.fullsize, assets_dir_full_path)
                if local_path: local_image_paths_list.append(local_path) 
                image_alts_list.append(img_view.alt or '')
            details['embed_local_image_paths'] = ','.join(local_image_paths_list)
            details['embed_image_alts'] = ','.join(image_alts_list)
        elif isinstance(post.embed, models.AppBskyEmbedExternal.View):
            details['embed_type'] = 'external'; details['embed_external_url'] = post.embed.external.uri; details['embed_external_title'] = post.embed.external.title; details['embed_external_description'] = post.embed.external.description
        elif isinstance(post.embed, models.AppBskyEmbedRecord.View): 
            if isinstance(post.embed.record, models.AppBskyEmbedRecord.ViewRecord) and hasattr(post.embed.record, 'uri') and post.embed.record.uri : 
                details['embed_type'] = 'quote_post'; details['embed_quote_post_uri'] = post.embed.record.uri
        elif isinstance(post.embed, models.AppBskyEmbedRecordWithMedia.View): 
            details['embed_type'] = 'record_with_media'
            if post.embed.media and isinstance(post.embed.media, models.AppBskyEmbedImages.View):
                for img_view in post.embed.media.images:
                    local_path = download_image(img_view.fullsize, assets_dir_full_path)
                    if local_path: local_image_paths_list.append(local_path)
                    image_alts_list.append(img_view.alt or '')
                details['embed_local_image_paths'] = ','.join(local_image_paths_list)
                details['embed_image_alts'] = ','.join(image_alts_list)
            if post.embed.record and isinstance(post.embed.record, models.AppBskyEmbedRecord.ViewRecord) and hasattr(post.embed.record, 'uri') and post.embed.record.uri:
                 details['embed_quote_post_uri'] = post.embed.record.uri
    return details

def fetch_all_user_posts_sync(sync_client, actor_to_fetch, profile_did_of_archived_user, profile_handle_of_archived_user, assets_dir_full_path):
    # ... (This function remains the same, it receives and passes assets_dir_full_path) ...
    all_posts_data = []; cursor = None; total_fetched_count = 0
    print(f"\nFetching posts for target profile: {profile_handle_of_archived_user} (Actor for API: {actor_to_fetch}, Target DID for context: {profile_did_of_archived_user})...")
    while True:
        try:
            author_feed_params = models.AppBskyFeedGetAuthorFeed.Params(actor=actor_to_fetch, limit=POSTS_PER_REQUEST_LIMIT, cursor=cursor)
            response_data = sync_client.app.bsky.feed.get_author_feed(params=author_feed_params)
            feed_items = response_data.feed; current_cursor = response_data.cursor
            if not feed_items: print("No more posts found or an empty feed segment."); break
            new_posts_count = 0
            for item_feed_view_post in feed_items:
                if item_feed_view_post.post:
                    print(f"  Processing post: {item_feed_view_post.post.uri}")
                    post_details = extract_post_details_for_csv(item_feed_view_post, profile_did_of_archived_user, profile_handle_of_archived_user, assets_dir_full_path)
                    all_posts_data.append(post_details)
                    new_posts_count += 1
            total_fetched_count += new_posts_count
            print(f"Fetched {new_posts_count} posts in this batch. Total so far: {total_fetched_count}")
            cursor = current_cursor
            if not cursor: print("Reached the end of the feed (no more cursor)."); break
            time.sleep(REQUEST_DELAY_SECONDS)
        except Exception as e:
            error_message = str(e)
            print(f"Error fetching posts: {error_message}")
            if "RateLimitExceeded" in error_message or "ratelimit" in error_message.lower(): print("Rate limit likely exceeded. Waiting for 60 seconds..."); time.sleep(60)
            elif "HTTPError: 401" in error_message or "AuthenticationRequired" in error_message: print("Authentication error (401/AuthRequired) during fetch. Session might be invalid."); return None
            elif "rsVySackLock" in error_message: print(f"Lexicon revision mismatch error. Your atproto SDK might be outdated: {error_message}"); return None
            else: print(f"An unexpected error occurred during fetch ({type(e).__name__}): {error_message}. Stopping fetch."); traceback.print_exc(); return None
    print(f"Finished fetching. Total items retrieved for {profile_handle_of_archived_user}: {len(all_posts_data)}")
    return all_posts_data

def save_posts_to_csv(posts_data, csv_full_filepath): # Now takes full path
    if not posts_data: print(f"No posts data to save to CSV."); return
    # (Fieldnames are the same as the last version)
    fieldnames = [
        'profile_user_handle', 'profile_user_did', 'item_type', 'uri', 'cid', 
        'created_at', 'text', 'langs', 'author_handle', 'author_did', 'author_display_name', 
        'author_local_avatar_path', 'reply_count', 'repost_count', 'like_count', 
        'reply_to_post_uri', 'reply_root_post_uri', 'embed_type', 'embed_local_image_paths', 
        'embed_image_alts', 'embed_external_url', 'embed_external_title', 
        'embed_external_description', 'embed_quote_post_uri'
    ]
    try:
        with open(csv_full_filepath, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames, extrasaction='ignore') 
            writer.writeheader();
            for post_row in posts_data: writer.writerow(post_row)
        print(f"Successfully saved {len(posts_data)} posts to {csv_full_filepath}")
    except IOError as e: print(f"Error saving posts to CSV file {csv_full_filepath}: {e}")

# organize_feed_for_threading (Same as before)
def organize_feed_for_threading(all_posts_data_list, profile_did_of_archived_user):
    if not all_posts_data_list: return []
    posts_by_uri = {post['uri']: post for post in all_posts_data_list}
    replies_to_parent = {}
    for post_data in all_posts_data_list:
        if post_data['author_did'] == profile_did_of_archived_user and post_data.get('reply_to_post_uri'):
            parent_uri = post_data['reply_to_post_uri']
            if parent_uri not in replies_to_parent: replies_to_parent[parent_uri] = []
            replies_to_parent[parent_uri].append(post_data)
    for parent_uri in replies_to_parent:
        replies_to_parent[parent_uri].sort(key=lambda p: p['created_at'])
    display_feed = []; processed_uris = set()
    def add_threaded_replies_recursive(parent_uri_to_check):
        if parent_uri_to_check in replies_to_parent:
            for reply_post in replies_to_parent[parent_uri_to_check]:
                if reply_post['uri'] not in processed_uris:
                    display_feed.append(reply_post); processed_uris.add(reply_post['uri'])
                    add_threaded_replies_recursive(reply_post['uri'])
    for post_data in all_posts_data_list:
        if post_data['uri'] not in processed_uris:
            display_feed.append(post_data); processed_uris.add(post_data['uri'])
            add_threaded_replies_recursive(post_data['uri'])
    return display_feed

def generate_html_timeline( # (Same as before, with the footer change)
    posts_data_list, target_profile_handle, html_full_filepath, # Now takes full path
    target_avatar_local_path=None, target_banner_local_path=None,
    followers_count=0, follows_count=0, posts_count=0, profile_description=""
):
    # ... (This function remains the same as the last full version with the authenticity footer)
    if not posts_data_list and not (target_avatar_local_path or target_banner_local_path) and not profile_description:
        print(f"No posts data or profile media/info to generate HTML for {target_profile_handle}.")
        return

    color_page_bg = "#161E27"; color_post_text = "#E5E7EB"; color_display_name = "#FFFFFF"
    color_handle_time_stats = "#8899A6"; color_link = "#1D9BF0"; color_separator = "#38444D"
    color_repost_text = "#A0AEC0"
    font_family = "system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, 'Open Sans', 'Helvetica Neue', sans-serif"
    archive_generation_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')

    html_content = f"""<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Bluesky Archive: @{html.escape(target_profile_handle)}</title><style>
        body {{ font-family: {font_family}; line-height: 1.5; margin: 0; background-color: {color_page_bg}; color: {color_post_text}; }}
        .profile-header {{ margin-bottom: 0px; position: relative; }}
        .profile-banner {{ width: 100%; background-color: {color_separator}; }}
        .profile-banner img {{ display: block; width: 100%; height: auto; aspect-ratio: 3 / 1; object-fit: cover; }}
        .profile-avatar-section {{ display: flex; align-items: flex-end; padding: 0 16px; margin-top: -40px; position: relative; z-index: 1; }}
        .profile-avatar img {{ width: 80px; height: 80px; border-radius: 50%; border: 4px solid {color_page_bg}; background-color: {color_handle_time_stats}; }}
        .profile-info {{ padding: 10px 16px 12px 16px; border-bottom: 1px solid {color_separator}; }}
        .profile-info h1 {{ margin: 0 0 2px 0; font-size: 1.4em; color: {color_display_name}; }}
        .profile-info .handle {{ font-size: 0.95em; color: {color_handle_time_stats}; margin-bottom: 8px; }}
        .profile-info .stats {{ font-size: 0.9em; color: {color_handle_time_stats}; margin-bottom: 8px; }}
        .profile-info .stats span {{ margin-right: 15px; }} .profile-info .stats strong {{ color: {color_post_text}; }}
        .profile-description {{ font-size: 0.95em; margin-bottom: 10px; white-space: pre-wrap; word-wrap: break-word; }}
        .timeline-container {{ max-width: 600px; margin: auto; }}
        .post-item {{ display: flex; padding: 12px 16px; border-bottom: 1px solid {color_separator}; }} .post-item:last-child {{ border-bottom: none; }}
        .avatar-column {{ width: 48px; margin-right: 12px; flex-shrink: 0; }}
        .avatar-column img {{ width: 40px; height: 40px; border-radius: 50%; background-color: {color_handle_time_stats}; }}
        .post-content-column {{ flex-grow: 1; min-width: 0; }}
        .repost-info {{ font-size: 0.85em; color: {color_repost_text}; margin-bottom: 4px; }} .repost-info a {{ color: inherit; text-decoration: none; }} .repost-info a:hover {{ text-decoration: underline; }}
        .post-author-line {{ display: flex; align-items: baseline; font-size: 0.95em; margin-bottom: 2px; }}
        .post-author-name {{ font-weight: bold; color: {color_display_name}; margin-right: 5px; word-break: break-all; }}
        .post-author-handle, .post-timestamp-sep, .post-timestamp {{ color: {color_handle_time_stats}; margin-right: 5px; white-space: nowrap; }}
        .post-author-handle a {{ color: inherit; text-decoration: none; }} .post-author-handle a:hover {{ text-decoration: underline; }}
        .post-timestamp a {{ color: {color_handle_time_stats}; text-decoration: none; }} .post-timestamp a:hover {{ text-decoration: underline; }}
        .reply-info {{ font-size: 0.85em; color: {color_handle_time_stats}; margin-bottom: 6px; }} .reply-info a {{ color: {color_link}; text-decoration: none; }} .reply-info a:hover {{ text-decoration: underline; }}
        .post-text {{ margin-bottom: 10px; white-space: pre-wrap; word-wrap: break-word; font-size: 0.95em; color: {color_post_text}; }} .post-text a {{ color: {color_link}; text-decoration: none; }} .post-text a:hover {{ text-decoration: underline; }}
        .post-embeds {{ margin-top: 10px; }} .post-embeds img {{ max-width: 100%; height: auto; display: block; margin-top: 8px; border-radius: 8px; border: 1px solid {color_separator}; }}
        .embed-external {{ border: 1px solid {color_separator}; padding: 10px 12px; margin-top: 10px; border-radius: 8px; background-color: transparent; }} .embed-external a {{ text-decoration: none; color: inherit; display: block; }}
        .embed-external strong {{ display: block; font-weight: bold; color: {color_post_text}; font-size: 0.9em; margin-bottom: 3px; }}
        .embed-external span {{ font-size: 0.85em; color: {color_handle_time_stats}; display: block; margin-bottom: 3px; }}
        .embed-external small {{ font-size: 0.8em; color: {color_handle_time_stats}; display: block; }}
        .embed-quote {{ border: 1px solid {color_separator}; padding: 10px 12px; margin-top: 10px; border-radius: 8px; }} .embed-quote p {{ margin: 0; font-size: 0.9em; }} .embed-quote a {{ color: {color_link}; text-decoration: none; }} .embed-quote a:hover {{ text-decoration: underline; }}
        .post-stats {{ font-size: 0.85em; color: {color_handle_time_stats}; margin-top: 10px; }} .post-stats span {{ margin-right: 15px; }}
        .archive-footer {{ text-align: center; padding: 20px; margin-top: 30px; border-top: 1px solid {color_separator}; font-size: 0.8em; color: {color_handle_time_stats}; }}
        .archive-footer p {{ margin: 5px 0; }} .archive-footer a {{ color: {color_link}; text-decoration: none; }} .archive-footer a:hover {{ text-decoration: underline; }}
    </style></head><body><div class="timeline-container"><div class="profile-header">"""
    html_content += '<div class="profile-banner">'
    if target_banner_local_path: html_content += f'<img src="{html.escape(target_banner_local_path)}" alt="Profile banner">'
    else: html_content += f'<div style="width: 100%; aspect-ratio: 3 / 1; background-color: {color_separator};"></div>'
    html_content += '</div>'
    html_content += '<div class="profile-avatar-section">'
    if target_avatar_local_path: html_content += f'<div class="profile-avatar"><img src="{html.escape(target_avatar_local_path)}" alt="Profile avatar"></div>'
    else: html_content += f'<div class="profile-avatar"><div style="width:80px; height:80px; border-radius:50%; background-color:{color_handle_time_stats};"></div></div>'
    html_content += '</div></div>' 
    html_content += f"""<div class="profile-info"><h1>{html.escape(target_profile_handle)}</h1><div class="handle">@{html.escape(target_profile_handle)}</div>
            <div class="stats">
                <span><strong>{followers_count:,}</strong> Followers</span>
                <span><strong>{follows_count:,}</strong> Following</span>
                <span><strong>{posts_count:,}</strong> Posts</span>
            </div>"""
    if profile_description: html_content += f'<div class="profile-description">{profile_description}</div>'
    html_content += '</div>'
    if posts_data_list:
        for post_data in posts_data_list:
            author_local_avatar = post_data.get('author_local_avatar_path', '') 
            avatar_html = f'<div style="width:40px; height:40px; border-radius:50%; background-color:{color_handle_time_stats};"></div>' 
            if author_local_avatar: avatar_html = f'<img src="{html.escape(author_local_avatar)}" alt="Avatar for {html.escape(post_data.get("author_handle", "")) }">'
            profile_user_h = html.escape(post_data.get('profile_user_handle', '')); item_type = html.escape(post_data.get('item_type', 'post'))
            author_display_name = html.escape(post_data.get('author_display_name', 'Unknown Author')); author_handle = html.escape(post_data.get('author_handle', 'unknown.bsky.social'))
            created_at_raw = post_data.get('created_at', ''); created_at_formatted = html.escape(created_at_raw)
            try: dt_obj = datetime.fromisoformat(created_at_raw.replace('Z', '+00:00')); created_at_formatted = dt_obj.strftime('%b %d, %Y ⋅ %I:%M %p UTC') 
            except ValueError: pass
            post_text_html = html.escape(post_data.get('text', '')).replace('\n', '<br>\n')
            reply_to_uri = post_data.get('reply_to_post_uri', ''); bsky_profile_uri_base = "https://bsky.app/profile/"
            post_uri_slug = post_data.get("uri", "").split("/")[-1]; full_post_link_on_bsky = f"{bsky_profile_uri_base}{author_handle}/post/{post_uri_slug}"
            html_content += f'<div class="post-item item-type-{item_type}"><div class="avatar-column">{avatar_html}</div><div class="post-content-column">'
            if item_type == 'repost': html_content += f'<div class="repost-info">♻️ <a href="{bsky_profile_uri_base}{profile_user_h}" target="_blank">@{profile_user_h}</a> reposted</div>'
            html_content += f'<div class="post-author-line"><span class="post-author-name">{author_display_name}</span><span class="post-author-handle"><a href="{bsky_profile_uri_base}{author_handle}" target="_blank">@{author_handle}</a></span><span class="post-timestamp-sep">·</span><span class="post-timestamp"><a href="{full_post_link_on_bsky}" target="_blank">{created_at_formatted}</a></span></div>'
            if item_type == 'reply' and reply_to_uri:
                try: reply_uri_parts = AtUri.from_str(reply_to_uri); reply_link = f"{bsky_profile_uri_base}{reply_uri_parts.hostname}/post/{reply_uri_parts.rkey}"; reply_link_text = f"@{reply_uri_parts.hostname}"
                except ValueError: reply_link = html.escape(reply_to_uri); reply_link_text = "original post"
                html_content += f'<div class="reply-info">↪️ Replying to <a href="{reply_link}" target="_blank">{html.escape(reply_link_text)}</a></div>'
            html_content += f'<div class="post-text">{post_text_html}</div><div class="post-embeds">'
            embed_type = post_data.get('embed_type', ''); local_image_paths_str = post_data.get('embed_local_image_paths', '')
            if local_image_paths_str and (embed_type == 'images' or embed_type == 'record_with_media'):
                local_image_paths = local_image_paths_str.split(','); image_alts_str = post_data.get('embed_image_alts', ''); image_alts = image_alts_str.split(',') if image_alts_str else [''] * len(local_image_paths)
                for i, local_img_path in enumerate(local_image_paths):
                    if local_img_path: alt_text = html.escape(image_alts[i] if i < len(image_alts) and image_alts[i] else 'Embedded image'); html_content += f'<img src="{html.escape(local_img_path)}" alt="{alt_text}">'
            if embed_type == 'external':
                ext_url = post_data.get('embed_external_url', '#'); ext_title = html.escape(post_data.get('embed_external_title', 'External Link')); ext_desc = html.escape(post_data.get('embed_external_description', '')); ext_domain = ''
                if ext_url != '#':
                    try: parsed_url = urlparse(ext_url); ext_domain = html.escape(parsed_url.netloc)
                    except: pass
                html_content += f'<div class="embed-external"><a href="{html.escape(ext_url)}" target="_blank" rel="noopener noreferrer">{(f"<small>{ext_domain}</small>" if ext_domain else "")}<strong>{ext_title}</strong><span>{ext_desc}</span></a></div>'
            quote_post_uri = post_data.get('embed_quote_post_uri', '')
            if quote_post_uri and (embed_type == 'quote_post' or embed_type == 'record_with_media'):
                try: quote_uri_parts = AtUri.from_str(quote_post_uri); quote_link_on_bsky = f"{bsky_profile_uri_base}{quote_uri_parts.hostname}/post/{quote_uri_parts.rkey}"; quote_author_handle = f"@{quote_uri_parts.hostname}"
                except ValueError: quote_link_on_bsky = html.escape(quote_post_uri); quote_author_handle = "quoted post"
                html_content += f'<div class="embed-quote"><p>🔁 Quoting <a href="{quote_link_on_bsky}" target="_blank">{html.escape(quote_author_handle)}</a> (<a href="{quote_link_on_bsky}" target="_blank" style="font-size:0.8em; color:{color_handle_time_stats};">view</a>)</p></div>'
            html_content += '</div>' 
            html_content += f'<div class="post-stats"><span>💬 {post_data.get("reply_count", 0)}</span> <span>♻️ {post_data.get("repost_count", 0)}</span> <span>❤️ {post_data.get("like_count", 0)}</span></div></div></div>'
    else:
        html_content += "<p style='text-align:center; padding: 20px;'>No posts found in this archive.</p>"
    html_content += f"""<div class="archive-footer">
            <p>Bluesky Archive v1.0</p><p>Generated on: {archive_generation_date}</p>
            <p>Original profile: <a href="https://bsky.app/profile/{html.escape(target_profile_handle)}" target="_blank">@{html.escape(target_profile_handle)}</a></p>
            <p>Archive generated using the Bluesky API (AT Protocol)</p>
        </div></div></body></html>"""
    try:
        with open(html_full_filepath, 'w', encoding='utf-8') as f: f.write(html_content)
        print(f"Successfully generated HTML timeline to {html_full_filepath}")
    except IOError as e: print(f"Error writing HTML file {html_full_filepath}: {e}")


# --- Main Execution ---
if __name__ == "__main__":
    logged_in_bluesky_handle, logged_in_app_password = load_credentials()
    if not logged_in_bluesky_handle or not logged_in_app_password: exit(1)
        
    client, runner_did, runner_handle = login_to_bluesky(logged_in_bluesky_handle, logged_in_app_password)
    if not client: print("Could not log in as script runner. Exiting."); exit(1)
        
    target_user_input = input("Enter the Bluesky handle OR DID of the user you want to archive (e.g., username.bsky.social or did:plc:xxxx): ").strip()
    if not target_user_input: print("No target user handle or DID provided. Exiting."); exit(1)
    
    archive_target_actor_for_api = target_user_input 
    resolved_target_did = None; resolved_target_handle_for_filenames = None 
    target_avatar_local_path = None; target_banner_local_path = None
    target_followers_count = 0; target_follows_count = 0; target_posts_count = 0; target_description = ""

    script_dir = os.path.dirname(os.path.abspath(__file__)) # Get directory where script is run

    print(f"\nAttempting to archive 'EVERYTHING' for target user: {target_user_input}")
    
    try:
        target_profile_details_obj = None 
        if target_user_input.startswith("did:"):
            resolved_target_did = target_user_input
            print(f"Input is a DID: {resolved_target_did}. Fetching profile...")
            target_profile_params = models.AppBskyActorGetProfile.Params(actor=resolved_target_did)
            target_profile_details_obj = client.app.bsky.actor.get_profile(params=target_profile_params)
            resolved_target_handle_for_filenames = target_profile_details_obj.handle
            print(f"Resolved handle for DID {resolved_target_did}: {resolved_target_handle_for_filenames}")
        else:
            resolved_target_handle_for_filenames = target_user_input.lower() # Normalize handle to lowercase
            print(f"Input is a handle: {resolved_target_handle_for_filenames}. Resolving to DID and fetching profile...")
            identity_params = models.ComAtprotoIdentityResolveHandle.Params(handle=resolved_target_handle_for_filenames)
            identity_response = client.com.atproto.identity.resolve_handle(params=identity_params)
            resolved_target_did = identity_response.did
            print(f"Resolved DID for {resolved_target_handle_for_filenames}: {resolved_target_did}")
            target_profile_params = models.AppBskyActorGetProfile.Params(actor=resolved_target_did)
            target_profile_details_obj = client.app.bsky.actor.get_profile(params=target_profile_params)
        
        # Create the main archive folder for this user and timestamp
        archive_timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        safe_profile_handle = resolved_target_handle_for_filenames.replace('.', '_').replace('@', '')
        main_archive_folder_name = f"{safe_profile_handle}_archive_{archive_timestamp}"
        main_archive_folder_path = os.path.join(script_dir, main_archive_folder_name)

        if not os.path.exists(main_archive_folder_path):
            os.makedirs(main_archive_folder_path)
            print(f"Created main archive directory: {main_archive_folder_path}")

        assets_full_path = os.path.join(main_archive_folder_path, ASSETS_FOLDER_NAME)
        if not os.path.exists(assets_full_path):
            try: os.makedirs(assets_full_path); print(f"Created assets sub-directory: {assets_full_path}")
            except OSError as e: print(f"Error creating assets sub-directory {assets_full_path}: {e}. Media might not be saved.")
        
        print(f"Archive will be saved in: {main_archive_folder_path}")
        print(f"Media assets will be saved to: {assets_full_path}")


        if target_profile_details_obj:
            target_followers_count = target_profile_details_obj.followers_count or 0
            target_follows_count = target_profile_details_obj.follows_count or 0
            target_posts_count = target_profile_details_obj.posts_count or 0
            raw_description = target_profile_details_obj.description or ""
            target_description = html.escape(raw_description).replace('\n', '<br>\n')
            if target_profile_details_obj.avatar:
                print(f"  Target avatar URL: {target_profile_details_obj.avatar}")
                local_path = download_image(target_profile_details_obj.avatar, assets_full_path)
                if local_path: target_avatar_local_path = local_path
            if target_profile_details_obj.banner:
                print(f"  Target banner URL: {target_profile_details_obj.banner}")
                local_path = download_image(target_profile_details_obj.banner, assets_full_path)
                if local_path: target_banner_local_path = local_path
        
        if resolved_target_did and resolved_target_handle_for_filenames:
            raw_posts_data = fetch_all_user_posts_sync(
                client, archive_target_actor_for_api, 
                resolved_target_did, resolved_target_handle_for_filenames,
                assets_full_path
            )
            if raw_posts_data is not None: 
                print("\nOrganizing posts for threaded display...")
                organized_display_feed = organize_feed_for_threading(raw_posts_data, resolved_target_did)
                print(f"Organization complete. Total items for display: {len(organized_display_feed)}")

                csv_full_filepath = os.path.join(main_archive_folder_path, OUTPUT_FILENAME_CSV)
                html_full_filepath = os.path.join(main_archive_folder_path, OUTPUT_FILENAME_HTML)

                save_posts_to_csv(organized_display_feed, csv_full_filepath)
                generate_html_timeline(
                    organized_display_feed, resolved_target_handle_for_filenames, html_full_filepath,
                    target_avatar_local_path, target_banner_local_path,
                    target_followers_count, target_follows_count, target_posts_count, target_description
                )
        else:
            print(f"Could not fully resolve target information for {target_user_input}. Cannot archive.")
    except models.ComAtprotoIdentityResolveHandle.XRPCError as e: 
        print(f"Error resolving handle for {target_user_input}: {getattr(e, 'message', str(e))} (Error: {getattr(e, 'error', 'Unknown')})")
    except models.AppBskyActorGetProfile.XRPCError as e: 
        print(f"Error fetching profile for {target_user_input}: {getattr(e, 'message', str(e))} (Error: {getattr(e, 'error', 'Unknown')})")
    except Exception as e:
        print(f"An unexpected error occurred while processing target {target_user_input}: {e}")
        traceback.print_exc() 
    print("\nArchiving process finished.")
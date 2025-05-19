from atproto import Client, models, AtUri
import csv
import time
import os
from datetime import datetime
import traceback # For more detailed error logging if needed
import configparser # Added for config.ini

# --- Configuration ---
CONFIG_FILE = 'config.ini' # Define the config file name
# OUTPUT_FILENAME_TEMPLATE will be used to generate the CSV filename.
# Each archive for a user will create its own CSV.
OUTPUT_FILENAME_TEMPLATE = "bluesky_archive_{user_identifier}.csv" 
POSTS_PER_REQUEST_LIMIT = 100
REQUEST_DELAY_SECONDS = 1

# --- Helper Functions ---

def load_credentials():
    """Loads Bluesky credentials from the config file."""
    config = configparser.ConfigParser()
    if not os.path.exists(CONFIG_FILE):
        print(f"Error: Credentials file '{CONFIG_FILE}' not found.")
        print(f"Please create '{CONFIG_FILE}' in the same directory as the script with your Bluesky handle and App Password:")
        print("""
[BlueskyCredentials]
handle = your_login_handle.bsky.social
app_password = xxxx-xxxx-xxxx-xxxx
        """)
        return None, None
    try:
        config.read(CONFIG_FILE)
        handle = config.get('BlueskyCredentials', 'handle')
        app_password = config.get('BlueskyCredentials', 'app_password')
        if not handle or not app_password or handle == "your_login_handle.bsky.social" or app_password == "xxxx-xxxx-xxxx-xxxx":
            print(f"Error: Please update your actual credentials in '{CONFIG_FILE}'.")
            return None, None
        return handle, app_password
    except (configparser.NoSectionError, configparser.NoOptionError) as e:
        print(f"Error reading credentials from '{CONFIG_FILE}': {e}")
        print("Please ensure the file has the [BlueskyCredentials] section with 'handle' and 'app_password' keys.")
        return None, None
    except Exception as e:
        print(f"An unexpected error occurred while loading credentials: {e}")
        return None, None

def login_to_bluesky(user_login_handle, app_password):
    client = Client()
    try:
        session_data = client.login(user_login_handle, app_password)
        runner_did = session_data.did
        runner_handle = session_data.handle
        profile_params = models.AppBskyActorGetProfile.Params(actor=runner_did)
        profile_details_response = client.app.bsky.actor.get_profile(params=profile_params)
        display_name = profile_details_response.display_name
        if not display_name:
            display_name = runner_handle
        print(f"Successfully logged in as script runner: {display_name} (@{runner_handle})")
        print(f"Script runner DID: {runner_did}")
        return client, runner_did, runner_handle
    except Exception as e:
        print(f"Login failed for script runner ({user_login_handle}): {e}")
        return None, None, None

def extract_post_details_for_csv(feed_view_post_item, profile_did, profile_handle):
    post = feed_view_post_item.post 
    record = post.record 
    original_author = post.author 
    item_type = "post" 
    if isinstance(feed_view_post_item.reason, models.AppBskyFeedDefs.ReasonRepost):
        if feed_view_post_item.reason.by.did == profile_did:
            item_type = "repost"
    elif hasattr(record, 'reply') and record.reply and record.reply.parent:
        if original_author.did == profile_did: 
            item_type = "reply"
    details = {
        'profile_user_handle': profile_handle, 'profile_user_did': profile_did, 'item_type': item_type,
        'uri': post.uri, 'cid': post.cid, 'author_did': original_author.did,
        'author_handle': original_author.handle, 'author_display_name': original_author.display_name,
        'text': record.text if hasattr(record, 'text') else '',
        'created_at': record.created_at if hasattr(record, 'created_at') else '',
        'langs': ','.join(record.langs) if hasattr(record, 'langs') and record.langs else '',
        'reply_count': post.reply_count if post.reply_count is not None else 0,
        'repost_count': post.repost_count if post.repost_count is not None else 0,
        'like_count': post.like_count if post.like_count is not None else 0,
        'reply_to_post_uri': record.reply.parent.uri if hasattr(record, 'reply') and record.reply and record.reply.parent else '',
        'reply_root_post_uri': record.reply.root.uri if hasattr(record, 'reply') and record.reply and record.reply.root else '',
        'embed_type': '', 'embed_image_urls': '', 'embed_image_alts': '', # Note: This CSV script does not download images
        'embed_external_url': '', 'embed_external_title': '', 'embed_external_description': '',
        'embed_quote_post_uri': ''
    }
    if isinstance(details['created_at'], datetime):
        details['created_at'] = details['created_at'].isoformat()
    elif isinstance(record, dict) and 'createdAt' in record: 
        details['created_at'] = record['createdAt']
    if post.embed:
        if isinstance(post.embed, models.AppBskyEmbedImages.View):
            details['embed_type'] = 'images'; details['embed_image_urls'] = ','.join([img.fullsize for img in post.embed.images]); details['embed_image_alts'] = ','.join([img.alt for img in post.embed.images])
        elif isinstance(post.embed, models.AppBskyEmbedExternal.View):
            details['embed_type'] = 'external'; details['embed_external_url'] = post.embed.external.uri; details['embed_external_title'] = post.embed.external.title; details['embed_external_description'] = post.embed.external.description
        elif isinstance(post.embed, models.AppBskyEmbedRecord.View): 
            if isinstance(post.embed.record, models.AppBskyEmbedRecord.ViewRecord) and hasattr(post.embed.record, 'uri') and post.embed.record.uri : 
                details['embed_type'] = 'quote_post'; details['embed_quote_post_uri'] = post.embed.record.uri
        elif isinstance(post.embed, models.AppBskyEmbedRecordWithMedia.View): 
            details['embed_type'] = 'record_with_media'
            if post.embed.media and isinstance(post.embed.media, models.AppBskyEmbedImages.View):
                details['embed_image_urls'] = ','.join([img.fullsize for img in post.embed.media.images]); details['embed_image_alts'] = ','.join([img.alt for img in post.embed.media.images])
            if post.embed.record and isinstance(post.embed.record, models.AppBskyEmbedRecord.ViewRecord) and hasattr(post.embed.record, 'uri') and post.embed.record.uri:
                 details['embed_quote_post_uri'] = post.embed.record.uri
    return details

def fetch_all_user_posts_sync(sync_client, actor_to_fetch, p_did, p_handle):
    all_posts_data = []
    cursor = None 
    total_fetched_count = 0
    print(f"\nFetching posts for target profile: {p_handle} (Actor for API: {actor_to_fetch}, Target DID for context: {p_did})...")
    while True:
        try:
            author_feed_params = models.AppBskyFeedGetAuthorFeed.Params(
                actor=actor_to_fetch,
                limit=POSTS_PER_REQUEST_LIMIT,
                cursor=cursor  
            )
            response_data = sync_client.app.bsky.feed.get_author_feed(
                params=author_feed_params 
            )
            feed_items = response_data.feed 
            current_cursor = response_data.cursor 
            if not feed_items:
                print("No more posts found or an empty feed segment.")
                break
            new_posts_count = 0
            for item_feed_view_post in feed_items: 
                if item_feed_view_post.post: 
                    post_details = extract_post_details_for_csv(item_feed_view_post, p_did, p_handle)
                    all_posts_data.append(post_details)
                    new_posts_count += 1
            total_fetched_count += new_posts_count
            print(f"Fetched {new_posts_count} posts in this batch. Total so far: {total_fetched_count}")
            cursor = current_cursor 
            if not cursor:
                print("Reached the end of the feed (no more cursor).")
                break
            time.sleep(REQUEST_DELAY_SECONDS)
        except Exception as e:
            error_message = str(e)
            print(f"Error fetching posts: {error_message}")
            if "RateLimitExceeded" in error_message or "ratelimit" in error_message.lower():
                print("Rate limit likely exceeded. Waiting for 60 seconds...")
                time.sleep(60)
            elif "HTTPError: 401" in error_message or "AuthenticationRequired" in error_message:
                print("Authentication error (401/AuthRequired) during fetch. Session might be invalid.")
                return None 
            elif "rsVySackLock" in error_message: 
                print(f"Lexicon revision mismatch error. Your atproto SDK might be outdated: {error_message}")
                return None
            else:
                print(f"An unexpected error occurred during fetch ({type(e).__name__}): {error_message}. Stopping fetch.")
                return None 
    print(f"Finished fetching. Total items retrieved for {p_handle}: {len(all_posts_data)}")
    return all_posts_data

def save_posts_to_csv(posts_data, user_identifier_for_filename):
    if not posts_data:
        print(f"No posts data to save for {user_identifier_for_filename}.")
        return
    
    # Ensure the filename is just the base, not a path if it's coming from main app structure
    base_filename_identifier = os.path.basename(user_identifier_for_filename)
    safe_user_id_for_filename = base_filename_identifier.replace('.', '_').replace('@', '').replace(':', '_')
    
    # This script will save the CSV in the current working directory
    # or you can define a specific output path here if needed.
    filename = OUTPUT_FILENAME_TEMPLATE.format(user_identifier=safe_user_id_for_filename)
    
    fieldnames = [ # These are the columns from your original CSV script
        'profile_user_handle', 'profile_user_did', 'item_type', 'uri', 'cid', 
        'created_at', 'text', 'langs', 'author_handle', 'author_did', 'author_display_name', 
        'reply_count', 'repost_count', 'like_count', 'reply_to_post_uri', 'reply_root_post_uri', 
        'embed_type', 'embed_image_urls', 'embed_image_alts', 'embed_external_url', 
        'embed_external_title', 'embed_external_description', 'embed_quote_post_uri'
    ]
    try:
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames, extrasaction='ignore') 
            writer.writeheader()
            for post_row in posts_data:
                writer.writerow(post_row)
        print(f"Successfully saved {len(posts_data)} posts to {filename}")
    except IOError as e:
        print(f"Error saving posts to CSV file {filename}: {e}")

# --- Main Execution ---
if __name__ == "__main__":
    # Load credentials from config file
    logged_in_bluesky_handle, logged_in_app_password = load_credentials()

    if not logged_in_bluesky_handle or not logged_in_app_password:
        # load_credentials() will print specific error messages
        exit(1)
        
    # Login as the script runner using credentials from config.ini
    client, runner_did, runner_handle = login_to_bluesky(logged_in_bluesky_handle, logged_in_app_password)

    if not client: 
        print("Could not log in as script runner. Exiting.")
        exit(1)
        
    target_user_input = input("Enter the Bluesky handle OR DID of the user you want to archive (e.g., username.bsky.social or did:plc:xxxx): ").strip()
    if not target_user_input:
        print("No target user handle or DID provided. Exiting.")
        exit(1)
        
    archive_target_actor_for_api = target_user_input 
    resolved_target_did = None
    resolved_target_handle_for_filename = None # For the CSV filename

    print(f"\nAttempting to archive 'EVERYTHING' for target user: {target_user_input}")
    try:
        # Resolve handle/DID and get profile details for context
        if target_user_input.startswith("did:"):
            resolved_target_did = target_user_input
            print(f"Input is a DID: {resolved_target_did}. Fetching profile to get handle...")
            target_profile_params = models.AppBskyActorGetProfile.Params(actor=resolved_target_did)
            target_profile_details = client.app.bsky.actor.get_profile(params=target_profile_params)
            resolved_target_handle_for_filename = target_profile_details.handle
            print(f"Resolved handle for DID {resolved_target_did}: {resolved_target_handle_for_filename}")
        else:
            resolved_target_handle_for_filename = target_user_input.lower() # Normalize handle
            print(f"Input is a handle: {resolved_target_handle_for_filename}. Resolving to DID...")
            identity_params = models.ComAtprotoIdentityResolveHandle.Params(handle=resolved_target_handle_for_filename)
            identity_response = client.com.atproto.identity.resolve_handle(params=identity_params)
            resolved_target_did = identity_response.did
            print(f"Resolved DID for {resolved_target_handle_for_filename}: {resolved_target_did}")
            # Optionally, fetch full profile if needed, but for CSV name, handle is enough if input was handle.
            # If DID was input, we already fetched profile.

        if resolved_target_did and resolved_target_handle_for_filename:
            # Fetch posts (this version doesn't download assets, so no assets_dir needed)
            target_user_posts_data = fetch_all_user_posts_sync(
                client, archive_target_actor_for_api, 
                resolved_target_did, resolved_target_handle_for_filename 
            )
            if target_user_posts_data is not None: 
                # Save to CSV in the current directory
                save_posts_to_csv(target_user_posts_data, resolved_target_handle_for_filename)
        else:
            print(f"Could not fully resolve target information for {target_user_input}. Cannot archive.")
    except models.ComAtprotoIdentityResolveHandle.XRPCError as e: 
        print(f"Error resolving handle for {target_user_input}: {getattr(e, 'message', str(e))} (Error: {getattr(e, 'error', 'Unknown')})")
        print("Please ensure the handle is correct and the user exists.")
    except models.AppBskyActorGetProfile.XRPCError as e: 
        print(f"Error fetching profile for {target_user_input}: {getattr(e, 'message', str(e))} (Error: {getattr(e, 'error', 'Unknown')})")
        print("Please ensure the identifier is correct and the user profile is accessible.")
    except Exception as e:
        print(f"An unexpected error occurred while processing target {target_user_input}: {e}")
        traceback.print_exc() # Print full traceback for unexpected errors
        
    print("\nArchiving process finished.")

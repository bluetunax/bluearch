# Bluesky Profile Archiver

A Python script to archive a Bluesky user's profile, including their posts, replies, reposts, and associated media (profile banner/avatar, post author avatars, embedded images). The archive is saved locally into a timestamped folder for the user, containing:

1.  An **HTML file** (`profile_archive.html`) that recreates the profile feed for offline viewing, styled to mimic the Bluesky interface.
2.  A **CSV file** (`archive_data.csv`) containing all the fetched post data in a structured format.
3.  An **`assets` subfolder** containing all downloaded images.

## Features

*   **Comprehensive Archiving:** Fetches original posts, replies by the user, and reposts made by the user.
*   **Media Localization:** Downloads and saves profile banner, profile avatar (for the main archived profile and for individual post authors), and images embedded in posts.
*   **Thread Organization:** Attempts to group replies made by the target user under their parent posts in the display order.
*   **Dual Output:**
    *   **HTML Timeline:** A browsable, offline HTML page with a user interface similar to Bluesky.
    *   **CSV Data:** For data analysis or other uses.
*   **Organized Output:** Each archive is saved in a dedicated folder named `[userhandle]_archive_[datetime]`.
*   **Secure Credential Management:** Uses a `config.ini` file (not to be committed) for Bluesky credentials.
*   **Interactive:** Prompts for the Bluesky handle or DID of the user to archive.

## Project Status

This script has reached a good functional state, successfully archiving profiles as described. Future enhancements can be found in the "Future Enhancements" section below.

## Prerequisites

*   **Python 3.8+** (developed with Python 3.10 in mind)
*   **Conda** (Recommended for managing environments, but `venv` can also be used)

## Setup and Installation

1.  **Clone the repository (or download the script):**
    ```bash
    git clone <your-repository-url>
    cd <repository-name>
    ```
    (If you're not using Git, just place `app.py` in a new project folder.)

2.  **Create and Activate a Conda Environment:**
    ```bash
    conda create --name bluesky_env python=3.10
    conda activate bluesky_env
    ```

3.  **Install Dependencies:**
    Install the required Python packages using the provided `requirements.txt` file:
    ```bash
    pip install -r requirements.txt
    ```
    (The `requirements.txt` should have been generated using `pip freeze > requirements.txt` in your working Conda environment and should include `atproto` and `requests` among others.)

## Configuration

1.  **Create `config.ini`:**
    In the root directory of the project (same place as `app.py`), create a file named `config.ini`.

2.  **Add Your Bluesky Credentials:**
    Open `config.ini` and add your Bluesky handle and an **App Password** (NOT your main account password). Generate an App Password from Bluesky app settings (Settings -> App Passwords).
    ```ini
    [BlueskyCredentials]
    handle = your_actual_login_handle.bsky.social
    app_password = your_actual_app_password_xxxx-xxxx-xxxx-xxxx
    ```
    Replace the placeholder values with your actual credentials.

3.  **Important Security Note:**
    **DO NOT commit your `config.ini` file to Git.** Add it to your `.gitignore` file:
    ```
    config.ini
    assets/
    *_archive_*/
    ```
    The `assets/` and `*_archive_*/` entries are to ignore the downloaded media and generated archive folders, which can become large.

## Usage

1.  Ensure your Conda environment (`bluesky_env`) is activated.
2.  Navigate to the project directory in your terminal.
3.  Run the script:
    ```bash
    python app.py
    ```
4.  The script will log in using the credentials from `config.ini`.
5.  You will be prompted to enter the Bluesky handle (e.g., `username.bsky.social`) or DID (e.g., `did:plc:xxxxxxxxxxxx`) of the user you wish to archive.
6.  The script will then fetch the data, download media, and create the archive folder.

## Output Structure

For each archival process, a new folder will be created in the script's directory with the following structure:
IGNORE_WHEN_COPYING_END

your_target_user_handle_archive_YYYYMMDD_HHMMSS/
├── assets/
│ ├── profile_banner_image_uuid.jpg
│ ├── profile_avatar_image_uuid.jpg
│ ├── post_author_avatar_uuid.jpg
│ └── embedded_post_image_uuid.jpg
│ └── ... (all other downloaded images)
├── archive_data.csv
└── profile_archive.html


*   **`assets/`**: Contains all downloaded images (profile pictures, banners, post images).
*   **`archive_data.csv`**: The structured CSV data of all posts.
*   **`profile_archive.html`**: The browsable HTML timeline.

## Threading Logic

The script attempts to organize the HTML output to display threads more naturally. When a post is displayed, any replies made *by the archived user* to that post (and subsequent replies by them in that thread) are displayed immediately following it. This is achieved by post-processing the initially fetched feed.

## Disclaimer

*   The Bluesky API is still evolving, and changes to the API may break this script.
*   Always be mindful of Bluesky's Terms of Service and API rate limits. This script includes basic delays, but excessive use could lead to temporary restrictions.
*   This tool is for personal archiving purposes. Respect data privacy and copyright.

## Contributing

Contributions, bug reports, and feature requests are welcome! Please feel free to open an issue or submit a pull request.

## License
MIT License

Copyright (c) 2025 [Bluetunax](https://github.com/bluetunax/)

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

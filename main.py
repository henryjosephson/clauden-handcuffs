"""Monitor work focus by analyzing screen content and providing reminders."""

import argparse
import base64
import os
import queue
import tempfile
import threading
import time
import tkinter as tk
from pathlib import Path

import anthropic
import mss
from dotenv import load_dotenv
from google import genai
from PIL import Image

load_dotenv()

# Model configurations
CLAUDE_MODEL = "claude-3-haiku-20240307"
GEMINI_MODEL = "gemini-2.0-flash"


class VisionAnalyzer:
    """Protocol for vision analysis implementations."""

    def analyze_image(self, image, prompt):
        """Analyze an image and return a response.

        Args:
            image: The image to analyze
            prompt: The prompt to use for analysis

        Returns:
            The model's response as a string
        """

    def generate_text(self, prompt):
        """Generate text based on a prompt.

        Args:
            prompt: The prompt to use for text generation

        Returns:
            The generated text as a string
        """


class ClaudeAnalyzer:
    """Claude vision analysis implementation."""

    def __init__(self):
        """Initialize Claude client."""
        self.client = anthropic.Anthropic()

    def analyze_image(self, image, prompt):
        """Analyze image using Claude."""
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp_file:
            image.save(tmp_file.name, "PNG")
            tmp_path = Path(tmp_file.name)
            image_bytes = tmp_path.read_bytes()
            image_base64 = base64.b64encode(image_bytes).decode("utf-8")

            response = self.client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=1024,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": prompt,
                            },
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/png",
                                    "data": image_base64,
                                },
                            },
                        ],
                    },
                ],
            )
            tmp_path.unlink()
            return response.content[0].text

    def generate_text(self, prompt):
        """Generate text using Claude."""
        response = self.client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=1024,
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
        )
        return response.content[0].text


class GeminiAnalyzer:
    """Gemini vision analysis implementation."""

    def __init__(self):
        """Initialize Gemini client."""
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY environment variable is required")
        self.client = genai.Client(api_key=api_key)

    def analyze_image(self, image, prompt):
        """Analyze image using Gemini."""
        response = self.client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[prompt, image],
        )
        return response.text

    def generate_text(self, prompt):
        """Generate text using Gemini."""
        response = self.client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
        )
        return response.text


class WorkMonitorApp:
    """Application that monitors work focus and displays overlay reminders."""

    def __init__(
        self,
        task_description,
        interval,
        model="gemini",
        *,
        verbose=False,
    ):
        """Initialize the work monitoring application.

        Args:
            task_description: Description of the task to monitor
            interval: Time between checks in seconds
            model: Vision model to use ("claude" or "gemini")
            verbose: Whether to enable debug logging
        """
        # Initialize main window but keep it hidden
        self.root = tk.Tk()
        self.root.withdraw()  # Hide the main window

        self.task_description = task_description
        self.interval = interval
        self.verbose = verbose
        self.queue = queue.Queue()
        self.overlay_visible = False
        self.overlays = []  # List to store multiple overlay windows

        # Initialize vision analyzer based on model choice
        self.analyzer = ClaudeAnalyzer() if model == "claude" else GeminiAnalyzer()

        # Start monitoring in a separate thread
        self.monitor_thread = threading.Thread(target=self.monitor_work, daemon=True)
        self.monitor_thread.start()

        # Schedule the first check
        self.root.after(100, self.check_queue)

    def log(self, message):
        """Log message if verbose mode is enabled.

        Args:
            message: Message to log
        """
        if self.verbose:
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            print(f"[DEBUG {timestamp}] {message}")

    def get_random_message(self):
        """Get a random apologetic message from the model.

        Returns:
            A randomly generated apologetic message
        """
        prompt = f"Generate a short apologetic message (1-2 sentences) from someone who got distracted instead of working on this task: '{self.task_description}'. Make it sincere and remorseful. Keep it under 100 characters. Only respond with the message, nothing else."
        message = self.analyzer.generate_text(prompt).strip()
        self.log(f"Generated message: {message}")
        return message

    def block_escape_attempts(self, event=None):
        """Block any attempt to close/minimize the window.

        Args:
            event: The event that triggered this handler (unused)

        Returns:
            String to prevent the event from propagating
        """
        return "break"

    def show_overlay(self):
        """Display overlay windows on all monitors with a message to type."""
        if self.overlay_visible:
            return

        self.log("Showing overlays")
        self.overlay_visible = True
        self.required_message = self.get_random_message()

        # Get screen information for all monitors
        with mss.mss() as mss_instance:
            monitors = mss_instance.monitors[
                1:
            ]  # Skip index 0 as it represents all monitors combined

        # Create an overlay for each monitor
        for i, monitor in enumerate(monitors):
            overlay = tk.Toplevel(self.root)
            overlay.geometry(
                f"{monitor['width']}x{monitor['height']}+{monitor['left']}+{monitor['top']}",
            )
            overlay.attributes("-fullscreen", True)  # noqa: FBT003, this is how tkinter works
            overlay.attributes("-topmost", True)  # noqa: FBT003, this is how tkinter works
            overlay.configure(bg="red")
            overlay.attributes("-alpha", 0.95)

            # Prevent window from being closed or minimized
            overlay.protocol("WM_DELETE_WINDOW", self.block_escape_attempts)
            overlay.overrideredirect(True)  # noqa: FBT003, this is how tkinter works -- remove window decorations

            # Disable all mouse inputs
            for mouse_event in [
                "<Button-1>",
                "<Button-2>",
                "<Button-3>",
                "<B1-Motion>",
                "<B2-Motion>",
                "<B3-Motion>",
                "<Motion>",
            ]:
                overlay.bind(mouse_event, self.block_escape_attempts)

            # Bind keys that might be used to escape
            for key in [
                "<Alt-F4>",
                "<Escape>",
                "<Control-w>",
                "<Control-W>",
                "<Control-c>",
                "<Control-C>",
                "<Command-q>",
                "<Command-Q>",
                "<Command-w>",
                "<Command-W>",
                "<Command-c>",
                "<Command-C>",
            ]:
                overlay.bind(key, self.block_escape_attempts)

            # Only show input fields on primary monitor (first one)
            if i == 0:
                main_label = tk.Label(
                    overlay,
                    text="GET BACK TO WORK",
                    font=("Arial", 72, "bold"),
                    bg="red",
                    fg="white",
                )
                main_label.pack(pady=50)

                message_label = tk.Label(
                    overlay,
                    text=f"Type this message to continue:\n\n{self.required_message}",
                    font=("Arial", 24),
                    bg="red",
                    fg="white",
                    wraplength=800,
                )
                message_label.pack(pady=30)

                self.entry = tk.Entry(overlay, font=("Arial", 18), width=50)
                self.entry.pack(pady=20)
                self.entry.focus_set()

                self.feedback_label = tk.Label(
                    overlay,
                    text="",
                    font=("Arial", 18),
                    bg="red",
                    fg="white",
                )
                self.feedback_label.pack(pady=10)

                overlay.bind("<Return>", self.check_input)
            else:
                # Show only the warning message on secondary monitors
                main_label = tk.Label(
                    overlay,
                    text="GET BACK TO WORK",
                    font=("Arial", 72, "bold"),
                    bg="red",
                    fg="white",
                )
                main_label.pack(expand=True)

            # Capture all input for this overlay
            overlay.grab_set()
            self.overlays.append(overlay)

    def check_input(self, event):
        """Check if the entered text matches the required message.

        Args:
            event: The event that triggered this handler (unused)
        """
        user_input = self.entry.get().strip()
        required = self.required_message.strip()
        # Remove quotes if present
        user_input = user_input.strip("\"'")
        required = required.strip("\"'")

        if user_input == required:
            self.log("Correct message entered, closing overlays")
            self.close_overlay()
        else:
            self.log(
                f"Incorrect message entered: '{user_input}' vs required: '{required}'",
            )
            self.feedback_label.config(text="Incorrect! Try again!")
            self.entry.delete(0, tk.END)

    def close_overlay(self):
        """Close all overlay windows."""
        for overlay in self.overlays:
            overlay.grab_release()
            overlay.destroy()
        self.overlays = []
        self.overlay_visible = False
        self.log("All overlays closed")

    def check_queue(self):
        """Check if we need to show the overlay."""
        try:
            show_overlay = self.queue.get_nowait()
            if show_overlay:
                self.show_overlay()
        except queue.Empty:
            pass
        finally:
            self.root.after(100, self.check_queue)

    def is_lock_screen(self, img):
        """Check if the lock screen is currently visible.

        Args:
            img: Screenshot image (unused)

        Returns:
            True if the overlay is visible, False otherwise
        """
        return self.overlay_visible

    def check_screenshot(self):
        """Take screenshot and check if it's consistent with the task.

        Returns:
            True if the user is on task or overlay is visible, False otherwise
        """
        if self.overlay_visible:
            self.log("Overlay is visible, skipping screenshot")
            return True

        self.log("Taking screenshot")
        with mss.mss() as mss_instance:
            # Combine screenshots from all monitors
            all_monitors = mss_instance.monitors[
                1:
            ]  # Skip index 0 as it represents all monitors combined
            screenshots = []
            for monitor in all_monitors:
                screenshot = mss_instance.grab(monitor)
                img = Image.frombytes(
                    "RGB",
                    screenshot.size,
                    screenshot.bgra,
                    "raw",
                    "BGRX",
                )
                screenshots.append(img)

            # Use the first screenshot for analysis
            img = screenshots[0] if screenshots else None
            if not img:
                return True

            if self.is_lock_screen(img):
                return True

            prompt = f"You're a diligent productivity checker whose job is to review my desktop and ensure I'm staying on-task. Is this image consistent with working on the following task: '{self.task_description}'? Answer with ONLY 'yes' or 'no'."

            response = self.analyzer.analyze_image(img, prompt)
            result = response.strip().lower() == "yes"
            self.log(f"Vision model response for on-task check: {result}")
            return result

    def monitor_work(self):
        """Continuously monitor work at specified interval."""
        try:
            while True:
                is_on_task = self.check_screenshot()
                if not is_on_task and not self.overlay_visible:
                    self.queue.put(True)  # noqa: FBT003, this is how tkinter works
                time.sleep(self.interval)
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(self.interval)

    def run(self):
        """Start the application."""
        print(f"Monitoring work for task: {self.task_description}")
        print(f"Checking every {self.interval} seconds")
        if self.verbose:
            print("Verbose logging enabled")
        print("Press Ctrl+C to stop monitoring")
        self.root.mainloop()


def main():
    """Run the work monitoring application."""
    parser = argparse.ArgumentParser(
        description="Monitor work focus based on screen content",
    )
    parser.add_argument(
        "--task",
        type=str,
        required=True,
        help="Description of the task you should be working on",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=60,
        help="Check interval in seconds (default: 60)",
    )
    parser.add_argument(
        "--model",
        type=str,
        choices=["claude", "gemini"],
        default="gemini",
        help="Vision model to use (default: gemini)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    app = WorkMonitorApp(
        args.task,
        args.interval,
        model=args.model,
        verbose=args.verbose,
    )
    try:
        app.run()
    except KeyboardInterrupt:
        print("\nStopping work monitoring...")


if __name__ == "__main__":
    main()

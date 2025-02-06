"""Monitor work focus by analyzing screen content and providing reminders."""

import argparse
import time
import tkinter as tk
from pathlib import Path
from PIL import ImageGrab, Image
import anthropic
import mss
import tempfile
from dotenv import load_dotenv
import base64
import queue
import threading

load_dotenv()
client = anthropic.Anthropic()

NANNY_MODEL = "claude-3-haiku-20240307"


class WorkMonitorApp:
    """Application that monitors work focus and displays overlay reminders."""

    def __init__(
        self, task_description: str, interval: int, *, verbose: bool = False
    ) -> None:
        """Initialize the work monitoring application.

        Args:
            task_description: Description of the task to monitor
            interval: Time between checks in seconds
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

        # Start monitoring in a separate thread
        self.monitor_thread = threading.Thread(target=self.monitor_work, daemon=True)
        self.monitor_thread.start()

        # Schedule the first check
        self.root.after(100, self.check_queue)

    def log(self, message: str) -> None:
        """Log message if verbose mode is enabled.

        Args:
            message: Message to log
        """
        if self.verbose:
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            print(f"[DEBUG {timestamp}] {message}")

    def get_random_message(self) -> str:
        """Get a random apologetic message from Claude.

        Returns:
            A randomly generated apologetic message
        """
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            messages=[
                {
                    "role": "user",
                    "content": f"Generate a short apologetic message (1-2 sentences) from someone who got distracted instead of working on this task: '{self.task_description}'. Make it sincere and remorseful. Keep it under 100 characters. Only respond with the message, nothing else.",
                }
            ],
        )
        message = response.content[0].text.strip()
        self.log(f"Generated message: {message}")
        return message

    def block_escape_attempts(self, event=None) -> str:
        """Block any attempt to close/minimize the window.

        Args:
            event: The event that triggered this handler (unused)

        Returns:
            String to prevent the event from propagating
        """
        return "break"

    def show_overlay(self) -> None:
        """Display the overlay window with a message to type."""
        if self.overlay_visible:
            return

        self.log("Showing overlay")
        self.overlay_visible = True
        self.required_message = self.get_random_message()

        self.overlay = tk.Toplevel(self.root)
        self.overlay.attributes("-fullscreen", True)
        self.overlay.attributes("-topmost", True)
        self.overlay.configure(bg="red")

        # Prevent window from being closed or minimized
        self.overlay.protocol("WM_DELETE_WINDOW", self.block_escape_attempts)
        self.overlay.attributes("-alpha", 0.95)

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
            self.overlay.bind(mouse_event, self.block_escape_attempts)

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
            self.overlay.bind(key, self.block_escape_attempts)

        main_label = tk.Label(
            self.overlay,
            text="GET BACK TO WORK",
            font=("Arial", 72, "bold"),
            bg="red",
            fg="white",
        )
        main_label.pack(pady=50)

        message_label = tk.Label(
            self.overlay,
            text=f"Type this message to continue:\n\n{self.required_message}",
            font=("Arial", 24),
            bg="red",
            fg="white",
            wraplength=800,
        )
        message_label.pack(pady=30)

        self.entry = tk.Entry(self.overlay, font=("Arial", 18), width=50)
        self.entry.pack(pady=20)
        self.entry.focus_set()

        self.feedback_label = tk.Label(
            self.overlay, text="", font=("Arial", 18), bg="red", fg="white"
        )
        self.feedback_label.pack(pady=10)

        self.overlay.bind("<Return>", self.check_input)

    def check_input(self, event) -> None:
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
            self.log("Correct message entered, closing overlay")
            self.close_overlay()
        else:
            self.log(
                f"Incorrect message entered: '{user_input}' vs required: '{required}'"
            )
            self.feedback_label.config(text="Incorrect! Try again!")
            self.entry.delete(0, tk.END)

    def close_overlay(self) -> None:
        """Close the overlay window."""
        if hasattr(self, "overlay"):
            self.overlay.destroy()
            self.overlay_visible = False
            self.log("Overlay closed")

    def check_queue(self) -> None:
        """Check if we need to show the overlay."""
        try:
            show_overlay = self.queue.get_nowait()
            if show_overlay:
                self.show_overlay()
        except queue.Empty:
            pass
        finally:
            self.root.after(100, self.check_queue)

    def is_lock_screen(self, img: Image.Image) -> bool:
        """Check if the lock screen is currently visible.

        Args:
            img: Screenshot image (unused)

        Returns:
            True if the overlay is visible, False otherwise
        """
        return self.overlay_visible

    def check_screenshot(self) -> bool:
        """Take screenshot and check if it's consistent with the task.

        Returns:
            True if the user is on task or overlay is visible, False otherwise
        """
        if self.overlay_visible:
            self.log("Overlay is visible, skipping screenshot")
            return True

        self.log("Taking screenshot")
        with mss.mss() as mss_instance:
            monitor = mss_instance.monitors[0]
            screenshot = mss_instance.grab(monitor)
            img = Image.frombytes(
                "RGB", screenshot.size, screenshot.bgra, "raw", "BGRX"
            )

            if self.is_lock_screen(img):
                return True

            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp_file:
                img.save(tmp_file.name, "PNG")
                tmp_path = Path(tmp_file.name)
                image_bytes = tmp_path.read_bytes()
                image_base64 = base64.b64encode(image_bytes).decode("utf-8")

                response = client.messages.create(
                    model=MODEL,
                    max_tokens=1024,
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": f"You're a diligent productivity checker whose job is to review my desktop and ensure I'm staying on-task. Is this image consistent with working on the following task: '{self.task_description}'? Answer with ONLY 'yes' or 'no'.",
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
                        }
                    ],
                )
                result = response.content[0].text.strip().lower() == "yes"
                self.log(f"Claude response for on-task check: {result}")
                return result

    def monitor_work(self) -> None:
        """Continuously monitor work at specified interval."""
        try:
            while True:
                is_on_task = self.check_screenshot()
                if not is_on_task and not self.overlay_visible:
                    self.queue.put(True)
                time.sleep(self.interval)
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(self.interval)

    def run(self) -> None:
        """Start the application."""
        print(f"Monitoring work for task: {self.task_description}")
        print(f"Checking every {self.interval} seconds")
        if self.verbose:
            print("Verbose logging enabled")
        print("Press Ctrl+C to stop monitoring")
        self.root.mainloop()


def main() -> None:
    """Run the work monitoring application."""
    parser = argparse.ArgumentParser(
        description="Monitor work focus based on screen content"
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
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    app = WorkMonitorApp(args.task, args.interval, verbose=args.verbose)
    try:
        app.run()
    except KeyboardInterrupt:
        print("\nStopping work monitoring...")


if __name__ == "__main__":
    main()

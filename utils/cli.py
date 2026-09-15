import sys

class CLI:
    @staticmethod
    def print_startup():
        print("\n====================================================")
        print("            [BOT] JARVIS / FRIDAY")
        print("====================================================\n")
        print("Welcome back!\n")
        print("Voice Assistant is ready.\n")
        print("------------------------------------------------\n")
        print("[MIC] Say something...")
        print("(Press Ctrl+C anytime to exit.)\n")
        print("------------------------------------------------\n")
        sys.stdout.flush()

    @staticmethod
    def print_listening():
        print("[MIC] Listening...\n")
        sys.stdout.flush()

    @staticmethod
    def print_processing():
        print("[PROC] Processing...\n")
        sys.stdout.flush()

    @staticmethod
    def print_user_input(text: str):
        print("You:")
        print(f"> {text}\n")
        sys.stdout.flush()

    @staticmethod
    def print_jarvis_response(text: str):
        print("JARVIS:")
        print(f"> {text}\n")
        print("------------------------------------------------\n")
        print("[MIC] Ready for next command...\n")
        sys.stdout.flush()

    @staticmethod
    def print_shutdown():
        print("\n------------------------------------------------\n")
        print("[BYE] Shutting down...\n")
        print("Thanks for using JARVIS.")
        print("Have a great day!\n")
        sys.stdout.flush()

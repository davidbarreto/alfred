from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IntentExample:
    text: str
    intent: str


INTENT_EXAMPLES: list[IntentExample] = [
    # --- task.add ---
    IntentExample(text="Remind me to call John tomorrow", intent="task.add"),
    IntentExample(text="Add a task to buy groceries", intent="task.add"),
    IntentExample(text="Create a to-do: review the pull requests", intent="task.add"),
    IntentExample(text="I need to schedule a dentist appointment", intent="task.add"),
    IntentExample(text="Don't forget to pay the electricity bill", intent="task.add"),
    IntentExample(text="Add buy flights to Paris to my task list", intent="task.add"),
    IntentExample(text="Remind me to send the weekly report on Friday", intent="task.add"),
    IntentExample(text="Task: prepare slides for the Monday presentation", intent="task.add"),
    IntentExample(text="I have to renew my passport", intent="task.add"),
    IntentExample(text="New task: follow up with the client about the proposal", intent="task.add"),

    # --- task.list ---
    IntentExample(text="What are my pending tasks?", intent="task.list"),
    IntentExample(text="Show me my to-do list", intent="task.list"),
    IntentExample(text="What do I have to do today?", intent="task.list"),
    IntentExample(text="List my high priority tasks", intent="task.list"),
    IntentExample(text="What tasks are overdue?", intent="task.list"),
    IntentExample(text="Show all my open tasks", intent="task.list"),
    IntentExample(text="Give me a summary of everything I need to do", intent="task.list"),
    IntentExample(text="What's on my task list?", intent="task.list"),

    # --- task.update ---
    IntentExample(text="Update task 42 to high priority", intent="task.update"),
    IntentExample(text="Change the deadline of task 7 to next Friday", intent="task.update"),
    IntentExample(text="Mark task 3 as in progress", intent="task.update"),
    IntentExample(text="Set task 5 status to blocked", intent="task.update"),
    IntentExample(text="Rename task 10 to fix the login bug", intent="task.update"),
    IntentExample(text="Edit task 2 and set priority to low", intent="task.update"),

    # --- task.complete ---
    IntentExample(text="Mark task 5 as done", intent="task.complete"),
    IntentExample(text="Complete task 12", intent="task.complete"),
    IntentExample(text="I finished task 8, mark it done", intent="task.complete"),
    IntentExample(text="Task 3 is complete", intent="task.complete"),
    IntentExample(text="Check off task 6", intent="task.complete"),
    IntentExample(text="I'm done with task 9", intent="task.complete"),

    # --- task.delete ---
    IntentExample(text="Delete task 10", intent="task.delete"),
    IntentExample(text="Remove task 3 from my list", intent="task.delete"),
    IntentExample(text="Cancel task 6", intent="task.delete"),
    IntentExample(text="Get rid of task 9", intent="task.delete"),
    IntentExample(text="Drop task 4, it's not needed anymore", intent="task.delete"),

    # --- note.add ---
    IntentExample(text="Take a note: meeting insights from today", intent="note.add"),
    IntentExample(text="Save this for later: the API key is abc123", intent="note.add"),
    IntentExample(text="Note: remember to check the deployment logs", intent="note.add"),
    IntentExample(text="Write down book recommendations from John", intent="note.add"),
    IntentExample(text="Jot this down: recipe for banana bread", intent="note.add"),
    IntentExample(text="Add a note about the architecture decision we made", intent="note.add"),
    IntentExample(text="Keep note: the meeting is at 2pm next Thursday", intent="note.add"),
    IntentExample(text="I want to remember this: always use async sessions in SQLAlchemy", intent="note.add"),

    # --- note.search ---
    IntentExample(text="Find my note about the API", intent="note.search"),
    IntentExample(text="Search for notes on travel", intent="note.search"),
    IntentExample(text="Do I have a note about Python tips?", intent="note.search"),
    IntentExample(text="Look for notes mentioning budget planning", intent="note.search"),
    IntentExample(text="Find notes related to the Docker setup", intent="note.search"),
    IntentExample(text="Search my notes for the password manager setup", intent="note.search"),

    # --- note.list ---
    IntentExample(text="Show all my notes", intent="note.list"),
    IntentExample(text="List recent notes", intent="note.list"),
    IntentExample(text="What notes do I have?", intent="note.list"),
    IntentExample(text="Display my saved notes", intent="note.list"),
    IntentExample(text="Give me all my notes", intent="note.list"),

    # --- note.update ---
    IntentExample(text="Edit note 3", intent="note.update"),
    IntentExample(text="Update the content of note 7", intent="note.update"),
    IntentExample(text="Change note 2 to include the new steps", intent="note.update"),
    IntentExample(text="Append to note 5: also check the staging environment", intent="note.update"),

    # --- note.delete ---
    IntentExample(text="Delete note 4", intent="note.delete"),
    IntentExample(text="Remove note 2", intent="note.delete"),
    IntentExample(text="Erase note 5, I don't need it anymore", intent="note.delete"),
    IntentExample(text="Get rid of note 8", intent="note.delete"),

    # --- event.add ---
    IntentExample(text="Schedule a meeting with Alice on Monday at 3pm", intent="event.add"),
    IntentExample(text="Add dentist appointment next Tuesday at 10am", intent="event.add"),
    IntentExample(text="Create a calendar event for team sync tomorrow", intent="event.add"),
    IntentExample(text="Book a call with the client on Friday at 2pm", intent="event.add"),
    IntentExample(text="Block 2pm to 3pm tomorrow for focused work", intent="event.add"),
    IntentExample(text="Put a reminder for the product review on Thursday", intent="event.add"),
    IntentExample(text="Schedule gym session every Monday at 7am", intent="event.add"),
    IntentExample(text="Add a recurring standup meeting every weekday at 9am", intent="event.add"),

    # --- event.list ---
    IntentExample(text="What's on my calendar today?", intent="event.list"),
    IntentExample(text="Show my schedule for next week", intent="event.list"),
    IntentExample(text="What events do I have this week?", intent="event.list"),
    IntentExample(text="Am I free on Thursday afternoon?", intent="event.list"),
    IntentExample(text="What meetings do I have tomorrow?", intent="event.list"),
    IntentExample(text="Show my upcoming events", intent="event.list"),
    IntentExample(text="What does my calendar look like this month?", intent="event.list"),

    # --- event.update ---
    IntentExample(text="Move event 5 to 4pm", intent="event.update"),
    IntentExample(text="Reschedule event 3 to next Monday", intent="event.update"),
    IntentExample(text="Change the dentist appointment to Wednesday", intent="event.update"),
    IntentExample(text="Update event 7, change title to sprint planning", intent="event.update"),
    IntentExample(text="Postpone the team sync by one hour", intent="event.update"),

    # --- event.delete ---
    IntentExample(text="Cancel event 2", intent="event.delete"),
    IntentExample(text="Delete the meeting scheduled on Tuesday", intent="event.delete"),
    IntentExample(text="Remove event 4 from my calendar", intent="event.delete"),
    IntentExample(text="Cancel the gym session on Friday", intent="event.delete"),
    IntentExample(text="I need to cancel my dentist appointment", intent="event.delete"),

    # --- finance.transaction_add ---
    IntentExample(text="I spent 45 dollars at the supermarket", intent="finance.transaction_add"),
    IntentExample(text="Add an expense: coffee shop 8 euros", intent="finance.transaction_add"),
    IntentExample(text="Record income of 2000 from freelancing this month", intent="finance.transaction_add"),
    IntentExample(text="Log a payment of 120 for the electricity bill", intent="finance.transaction_add"),
    IntentExample(text="Track expense: Netflix subscription 15.99", intent="finance.transaction_add"),
    IntentExample(text="I received a salary of 3500 euros", intent="finance.transaction_add"),
    IntentExample(text="Add transaction: lunch 12.50 euros", intent="finance.transaction_add"),
    IntentExample(text="Just paid 60 for a taxi ride", intent="finance.transaction_add"),
    IntentExample(text="Bought new headphones for 150 euros", intent="finance.transaction_add"),

    # --- finance.transaction_list ---
    IntentExample(text="Show my recent transactions", intent="finance.transaction_list"),
    IntentExample(text="What did I spend last week?", intent="finance.transaction_list"),
    IntentExample(text="List all expenses this month", intent="finance.transaction_list"),
    IntentExample(text="Show income transactions", intent="finance.transaction_list"),
    IntentExample(text="What transactions have I recorded?", intent="finance.transaction_list"),
    IntentExample(text="Show me all my purchases from this week", intent="finance.transaction_list"),

    # --- finance.spending_report ---
    IntentExample(text="How much did I spend this month?", intent="finance.spending_report"),
    IntentExample(text="Give me a spending report", intent="finance.spending_report"),
    IntentExample(text="What's my total spending for November?", intent="finance.spending_report"),
    IntentExample(text="Show my expenses breakdown", intent="finance.spending_report"),
    IntentExample(text="What categories did I spend most on last month?", intent="finance.spending_report"),
    IntentExample(text="How much have I spent so far this year?", intent="finance.spending_report"),
    IntentExample(text="Give me a financial overview for last quarter", intent="finance.spending_report"),

    # --- finance.spending_average ---
    IntentExample(text="What's my average monthly spending?", intent="finance.spending_average"),
    IntentExample(text="How much do I spend on average per week?", intent="finance.spending_average"),
    IntentExample(text="Show average spending on food", intent="finance.spending_average"),
    IntentExample(text="What's my typical grocery bill per month?", intent="finance.spending_average"),
    IntentExample(text="What do I spend on average on transport?", intent="finance.spending_average"),

    # --- finance.spending_top ---
    IntentExample(text="What are my top expenses?", intent="finance.spending_top"),
    IntentExample(text="Where am I spending the most?", intent="finance.spending_top"),
    IntentExample(text="Show my biggest expense categories", intent="finance.spending_top"),
    IntentExample(text="What are the top 5 things I spend on?", intent="finance.spending_top"),
    IntentExample(text="Which merchants do I spend the most at?", intent="finance.spending_top"),

    # --- finance.budget_add ---
    IntentExample(text="Set a budget of 500 euros for groceries", intent="finance.budget_add"),
    IntentExample(text="Create a monthly food budget of 300", intent="finance.budget_add"),
    IntentExample(text="Add a 200 euro transport budget for this month", intent="finance.budget_add"),
    IntentExample(text="Set up an entertainment budget of 100 per month", intent="finance.budget_add"),
    IntentExample(text="I want to limit my restaurant spending to 150 a month", intent="finance.budget_add"),

    # --- finance.budget_list ---
    IntentExample(text="Show my budgets", intent="finance.budget_list"),
    IntentExample(text="What budgets have I set?", intent="finance.budget_list"),
    IntentExample(text="List all my spending limits", intent="finance.budget_list"),
    IntentExample(text="What are my active budgets?", intent="finance.budget_list"),
    IntentExample(text="Show all budget categories", intent="finance.budget_list"),

    # --- finance.budget_remaining ---
    IntentExample(text="How much budget do I have left?", intent="finance.budget_remaining"),
    IntentExample(text="What's remaining in my grocery budget?", intent="finance.budget_remaining"),
    IntentExample(text="How much can I still spend this month?", intent="finance.budget_remaining"),
    IntentExample(text="Am I over budget on food?", intent="finance.budget_remaining"),
    IntentExample(text="How close am I to my entertainment limit?", intent="finance.budget_remaining"),
    IntentExample(text="What's left in my transport budget?", intent="finance.budget_remaining"),

    # --- finance.balance_forecast ---
    IntentExample(text="What will my balance be at the end of the month?", intent="finance.balance_forecast"),
    IntentExample(text="Forecast my financial situation for next quarter", intent="finance.balance_forecast"),
    IntentExample(text="Predict my cash flow for the next 30 days", intent="finance.balance_forecast"),
    IntentExample(text="How much money will I have left next month?", intent="finance.balance_forecast"),
    IntentExample(text="Give me a financial projection for the rest of the year", intent="finance.balance_forecast"),

    # --- unknown ---
    IntentExample(text="What's the weather like today?", intent="unknown"),
    IntentExample(text="Tell me a joke", intent="unknown"),
    IntentExample(text="How is the stock market doing?", intent="unknown"),
    IntentExample(text="What time is it in Tokyo?", intent="unknown"),
    IntentExample(text="Translate hello to French", intent="unknown"),
    IntentExample(text="Who won the football match last night?", intent="unknown"),
    IntentExample(text="What's the capital of Brazil?", intent="unknown"),
    IntentExample(text="Play some music", intent="unknown"),
    IntentExample(text="Write a poem about autumn", intent="unknown"),
    IntentExample(text="How tall is Mount Everest?", intent="unknown"),
    IntentExample(text="Give me a recipe for pasta carbonara", intent="unknown"),
    IntentExample(text="What's the latest news?", intent="unknown"),
]

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IntentExample:
    id: int
    text: str
    intent: str


INTENT_EXAMPLES: list[IntentExample] = [
    # --- task.add ---
    IntentExample(id=1,  text="Remind me to call John tomorrow", intent="task.add"),
    IntentExample(id=2,  text="Add a task to buy groceries", intent="task.add"),
    IntentExample(id=3,  text="Create a to-do: review the pull requests", intent="task.add"),
    IntentExample(id=4,  text="I need to schedule a dentist appointment", intent="task.add"),
    IntentExample(id=5,  text="Don't forget to pay the electricity bill", intent="task.add"),
    IntentExample(id=6,  text="Add buy flights to Paris to my task list", intent="task.add"),
    IntentExample(id=7,  text="Remind me to send the weekly report on Friday", intent="task.add"),
    IntentExample(id=8,  text="Task: prepare slides for the Monday presentation", intent="task.add"),
    IntentExample(id=9,  text="I have to renew my passport", intent="task.add"),
    IntentExample(id=10, text="New task: follow up with the client about the proposal", intent="task.add"),
    IntentExample(id=159, text="I need to buy milk on Monday", intent="shopping.add"),
    IntentExample(id=160, text="I have to pick up the kids after school today", intent="task.add"),
    IntentExample(id=161, text="Need to get a haircut this week", intent="task.add"),
    IntentExample(id=162, text="I should call the bank tomorrow morning", intent="task.add"),
    IntentExample(id=163, text="Don't let me forget to water the plants on Sunday", intent="task.add"),
    IntentExample(id=164, text="Buy a birthday present for mom before Friday", intent="task.add"),
    IntentExample(id=165, text="I need to take out the trash tonight", intent="task.add"),
    IntentExample(id=166, text="I want to buy beans", intent="shopping.add"),
    IntentExample(id=167, text="I need to buy eggs", intent="shopping.add"),
    IntentExample(id=168, text="I want to buy coffee at the supermarket", intent="shopping.add"),
    IntentExample(id=169, text="I need to get some bread", intent="shopping.add"),
    IntentExample(id=170, text="I want to buy a new book", intent="shopping.add"),
    IntentExample(id=171, text="Need to pick up vegetables at the market", intent="shopping.add"),
    IntentExample(id=172, text="I want to buy beans at Pingo Doce", intent="shopping.add"),

    # --- task.list ---
    IntentExample(id=11, text="What are my pending tasks?", intent="task.list"),
    IntentExample(id=12, text="Show me my to-do list", intent="task.list"),
    IntentExample(id=13, text="What do I have to do today?", intent="task.list"),
    IntentExample(id=14, text="List my high priority tasks", intent="task.list"),
    IntentExample(id=15, text="What tasks are overdue?", intent="task.list"),
    IntentExample(id=16, text="Show all my open tasks", intent="task.list"),
    IntentExample(id=17, text="Give me a summary of everything I need to do", intent="task.list"),
    IntentExample(id=18, text="What's on my task list?", intent="task.list"),

    # --- task.update ---
    IntentExample(id=19, text="Update task 42 to high priority", intent="task.update"),
    IntentExample(id=20, text="Change the deadline of task 7 to next Friday", intent="task.update"),
    IntentExample(id=21, text="Mark task 3 as in progress", intent="task.update"),
    IntentExample(id=22, text="Set task 5 status to blocked", intent="task.update"),
    IntentExample(id=23, text="Rename task 10 to fix the login bug", intent="task.update"),
    IntentExample(id=24, text="Edit task 2 and set priority to low", intent="task.update"),

    # --- task.complete ---
    IntentExample(id=25, text="Mark task 5 as done", intent="task.complete"),
    IntentExample(id=26, text="Complete task 12", intent="task.complete"),
    IntentExample(id=27, text="I finished task 8, mark it done", intent="task.complete"),
    IntentExample(id=28, text="Task 3 is complete", intent="task.complete"),
    IntentExample(id=29, text="Check off task 6", intent="task.complete"),
    IntentExample(id=30, text="I'm done with task 9", intent="task.complete"),

    # --- task.delete ---
    IntentExample(id=31, text="Delete task 10", intent="task.delete"),
    IntentExample(id=32, text="Remove task 3 from my list", intent="task.delete"),
    IntentExample(id=33, text="Cancel task 6", intent="task.delete"),
    IntentExample(id=34, text="Get rid of task 9", intent="task.delete"),
    IntentExample(id=35, text="Drop task 4, it's not needed anymore", intent="task.delete"),

    # --- note.add ---
    IntentExample(id=36, text="Take a note: meeting insights from today", intent="note.add"),
    IntentExample(id=37, text="Save this for later: the API key is abc123", intent="note.add"),
    IntentExample(id=38, text="Note: remember to check the deployment logs", intent="note.add"),
    IntentExample(id=39, text="Write down book recommendations from John", intent="note.add"),
    IntentExample(id=40, text="Jot this down: recipe for banana bread", intent="note.add"),
    IntentExample(id=41, text="Add a note about the architecture decision we made", intent="note.add"),
    IntentExample(id=42, text="Keep note: the meeting is at 2pm next Thursday", intent="note.add"),
    IntentExample(id=43, text="I want to remember this: always use async sessions in SQLAlchemy", intent="note.add"),
    IntentExample(id=203, text="Create a note to move all LLM calls from n8n to FastAPI", intent="note.add"),
    IntentExample(id=204, text="Create a note about refactoring the auth middleware", intent="note.add"),
    IntentExample(id=205, text="Make a note to review the deployment pipeline", intent="note.add"),
    IntentExample(id=206, text="Make a note: switch the database to async connections", intent="note.add"),
    IntentExample(id=207, text="Create a note to migrate the worker jobs to the new queue", intent="note.add"),

    # --- note.search ---
    IntentExample(id=44, text="Find my note about the API", intent="note.search"),
    IntentExample(id=45, text="Search for notes on travel", intent="note.search"),
    IntentExample(id=46, text="Do I have a note about Python tips?", intent="note.search"),
    IntentExample(id=47, text="Look for notes mentioning budget planning", intent="note.search"),
    IntentExample(id=48, text="Find notes related to the Docker setup", intent="note.search"),
    IntentExample(id=49, text="Search my notes for the password manager setup", intent="note.search"),

    # --- note.list ---
    IntentExample(id=50, text="Show all my notes", intent="note.list"),
    IntentExample(id=51, text="List recent notes", intent="note.list"),
    IntentExample(id=52, text="What notes do I have?", intent="note.list"),
    IntentExample(id=53, text="Display my saved notes", intent="note.list"),
    IntentExample(id=54, text="Give me all my notes", intent="note.list"),

    # --- note.update ---
    IntentExample(id=55, text="Edit note 3", intent="note.update"),
    IntentExample(id=56, text="Update the content of note 7", intent="note.update"),
    IntentExample(id=57, text="Change note 2 to include the new steps", intent="note.update"),
    IntentExample(id=58, text="Append to note 5: also check the staging environment", intent="note.update"),

    # --- note.delete ---
    IntentExample(id=59, text="Delete note 4", intent="note.delete"),
    IntentExample(id=60, text="Remove note 2", intent="note.delete"),
    IntentExample(id=61, text="Erase note 5, I don't need it anymore", intent="note.delete"),
    IntentExample(id=62, text="Get rid of note 8", intent="note.delete"),

    # --- event.add ---
    IntentExample(id=63, text="Schedule a meeting with Alice on Monday at 3pm", intent="event.add"),
    IntentExample(id=64, text="Add dentist appointment next Tuesday at 10am", intent="event.add"),
    IntentExample(id=65, text="Create a calendar event for team sync tomorrow", intent="event.add"),
    IntentExample(id=66, text="Book a call with the client on Friday at 2pm", intent="event.add"),
    IntentExample(id=67, text="Block 2pm to 3pm tomorrow for focused work", intent="event.add"),
    IntentExample(id=68, text="Put a reminder for the product review on Thursday", intent="event.add"),
    IntentExample(id=69, text="Schedule gym session every Monday at 7am", intent="event.add"),
    IntentExample(id=70, text="Add a recurring standup meeting every weekday at 9am", intent="event.add"),
    IntentExample(id=153, text="Can you create an event for next Sunday at 3pm?", intent="event.add"),
    IntentExample(id=154, text="Can you add something to my calendar for Saturday?", intent="event.add"),
    IntentExample(id=155, text="I need to create an event called team lunch next Friday", intent="event.add"),
    IntentExample(id=156, text="Please add a 1-hour event for the capoeira class on Sunday", intent="event.add"),
    IntentExample(id=157, text="Can you put a birthday party on my calendar for next Saturday at 6pm?", intent="event.add"),
    IntentExample(id=158, text="I have a doctor visit next Monday at 9am, can you add it?", intent="event.add"),

    # --- event.list ---
    IntentExample(id=71, text="What's on my calendar today?", intent="event.list"),
    IntentExample(id=72, text="Show my schedule for next week", intent="event.list"),
    IntentExample(id=73, text="What events do I have this week?", intent="event.list"),
    IntentExample(id=74, text="Am I free on Thursday afternoon?", intent="event.list"),
    IntentExample(id=75, text="What meetings do I have tomorrow?", intent="event.list"),
    IntentExample(id=76, text="Show my upcoming events", intent="event.list"),
    IntentExample(id=77, text="What does my calendar look like this month?", intent="event.list"),

    # --- event.update ---
    IntentExample(id=78, text="Move event 5 to 4pm", intent="event.update"),
    IntentExample(id=79, text="Reschedule event 3 to next Monday", intent="event.update"),
    IntentExample(id=80, text="Change the dentist appointment to Wednesday", intent="event.update"),
    IntentExample(id=81, text="Update event 7, change title to sprint planning", intent="event.update"),
    IntentExample(id=82, text="Postpone the team sync by one hour", intent="event.update"),

    # --- event.delete ---
    IntentExample(id=83, text="Cancel event 2", intent="event.delete"),
    IntentExample(id=84, text="Delete the meeting scheduled on Tuesday", intent="event.delete"),
    IntentExample(id=85, text="Remove event 4 from my calendar", intent="event.delete"),
    IntentExample(id=86, text="Cancel the gym session on Friday", intent="event.delete"),
    IntentExample(id=87, text="I need to cancel my dentist appointment", intent="event.delete"),

    # --- finance.transaction_add ---
    IntentExample(id=88,  text="I spent 45 dollars at the supermarket", intent="finance.transaction_add"),
    IntentExample(id=89,  text="Add an expense: coffee shop 8 euros", intent="finance.transaction_add"),
    IntentExample(id=90,  text="Record income of 2000 from freelancing this month", intent="finance.transaction_add"),
    IntentExample(id=91,  text="Log a payment of 120 for the electricity bill", intent="finance.transaction_add"),
    IntentExample(id=92,  text="Track expense: Netflix subscription 15.99", intent="finance.transaction_add"),
    IntentExample(id=93,  text="I received a salary of 3500 euros", intent="finance.transaction_add"),
    IntentExample(id=94,  text="Add transaction: lunch 12.50 euros", intent="finance.transaction_add"),
    IntentExample(id=95,  text="Just paid 60 for a taxi ride", intent="finance.transaction_add"),
    IntentExample(id=96,  text="Bought new headphones for 150 euros", intent="finance.transaction_add"),

    # --- finance.transaction_list ---
    IntentExample(id=97,  text="Show my recent transactions", intent="finance.transaction_list"),
    IntentExample(id=98,  text="What did I spend last week?", intent="finance.transaction_list"),
    IntentExample(id=99,  text="List all expenses this month", intent="finance.transaction_list"),
    IntentExample(id=100, text="Show income transactions", intent="finance.transaction_list"),
    IntentExample(id=101, text="What transactions have I recorded?", intent="finance.transaction_list"),
    IntentExample(id=102, text="Show me all my purchases from this week", intent="finance.transaction_list"),

    # --- finance.spending_report ---
    IntentExample(id=103, text="How much did I spend this month?", intent="finance.spending_report"),
    IntentExample(id=104, text="Give me a spending report", intent="finance.spending_report"),
    IntentExample(id=105, text="What's my total spending for November?", intent="finance.spending_report"),
    IntentExample(id=106, text="Show my expenses breakdown", intent="finance.spending_report"),
    IntentExample(id=107, text="What categories did I spend most on last month?", intent="finance.spending_report"),
    IntentExample(id=108, text="How much have I spent so far this year?", intent="finance.spending_report"),
    IntentExample(id=109, text="Give me a financial overview for last quarter", intent="finance.spending_report"),

    # --- finance.spending_average ---
    IntentExample(id=110, text="What's my average monthly spending?", intent="finance.spending_average"),
    IntentExample(id=111, text="How much do I spend on average per week?", intent="finance.spending_average"),
    IntentExample(id=112, text="Show average spending on food", intent="finance.spending_average"),
    IntentExample(id=113, text="What's my typical grocery bill per month?", intent="finance.spending_average"),
    IntentExample(id=114, text="What do I spend on average on transport?", intent="finance.spending_average"),

    # --- finance.spending_top ---
    IntentExample(id=115, text="What are my top expenses?", intent="finance.spending_top"),
    IntentExample(id=116, text="Where am I spending the most?", intent="finance.spending_top"),
    IntentExample(id=117, text="Show my biggest expense categories", intent="finance.spending_top"),
    IntentExample(id=118, text="What are the top 5 things I spend on?", intent="finance.spending_top"),
    IntentExample(id=119, text="Which merchants do I spend the most at?", intent="finance.spending_top"),

    # --- finance.budget_add ---
    IntentExample(id=120, text="Set a budget of 500 euros for groceries", intent="finance.budget_add"),
    IntentExample(id=121, text="Create a monthly food budget of 300", intent="finance.budget_add"),
    IntentExample(id=122, text="Add a 200 euro transport budget for this month", intent="finance.budget_add"),
    IntentExample(id=123, text="Set up an entertainment budget of 100 per month", intent="finance.budget_add"),
    IntentExample(id=124, text="I want to limit my restaurant spending to 150 a month", intent="finance.budget_add"),

    # --- finance.budget_list ---
    IntentExample(id=125, text="Show my budgets", intent="finance.budget_list"),
    IntentExample(id=126, text="What budgets have I set?", intent="finance.budget_list"),
    IntentExample(id=127, text="List all my spending limits", intent="finance.budget_list"),
    IntentExample(id=128, text="What are my active budgets?", intent="finance.budget_list"),
    IntentExample(id=129, text="Show all budget categories", intent="finance.budget_list"),

    # --- finance.budget_remaining ---
    IntentExample(id=130, text="How much budget do I have left?", intent="finance.budget_remaining"),
    IntentExample(id=131, text="What's remaining in my grocery budget?", intent="finance.budget_remaining"),
    IntentExample(id=132, text="How much can I still spend this month?", intent="finance.budget_remaining"),
    IntentExample(id=133, text="Am I over budget on food?", intent="finance.budget_remaining"),
    IntentExample(id=134, text="How close am I to my entertainment limit?", intent="finance.budget_remaining"),
    IntentExample(id=135, text="What's left in my transport budget?", intent="finance.budget_remaining"),

    # --- finance.balance_forecast ---
    IntentExample(id=136, text="What will my balance be at the end of the month?", intent="finance.balance_forecast"),
    IntentExample(id=137, text="Forecast my financial situation for next quarter", intent="finance.balance_forecast"),
    IntentExample(id=138, text="Predict my cash flow for the next 30 days", intent="finance.balance_forecast"),
    IntentExample(id=139, text="How much money will I have left next month?", intent="finance.balance_forecast"),
    IntentExample(id=140, text="Give me a financial projection for the rest of the year", intent="finance.balance_forecast"),

    # --- shopping.add ---
    IntentExample(id=173, text="Add milk to my shopping list", intent="shopping.add"),
    IntentExample(id=174, text="Put bread on the shopping list", intent="shopping.add"),
    IntentExample(id=175, text="Add 2 bottles of olive oil to groceries", intent="shopping.add"),
    IntentExample(id=176, text="I want to buy detergent", intent="shopping.add"),
    IntentExample(id=177, text="I need to get shampoo at the pharmacy", intent="shopping.add"),

    # --- shopping.list ---
    IntentExample(id=178, text="Show my shopping list", intent="shopping.list"),
    IntentExample(id=179, text="What do I need to buy?", intent="shopping.list"),
    IntentExample(id=180, text="What's on my grocery list?", intent="shopping.list"),

    # --- shopping.complete ---
    IntentExample(id=181, text="I bought milk", intent="shopping.complete"),
    IntentExample(id=182, text="Mark eggs as bought", intent="shopping.complete"),
    IntentExample(id=183, text="I got the bread from the supermarket", intent="shopping.complete"),

    # --- shopping.delete ---
    IntentExample(id=184, text="Remove milk from my shopping list", intent="shopping.delete"),
    IntentExample(id=185, text="Delete eggs from the shopping list", intent="shopping.delete"),
    IntentExample(id=186, text="Take shampoo off the shopping list", intent="shopping.delete"),

    # --- shopping.update ---
    IntentExample(id=187, text="Change the quantity of eggs to 6", intent="shopping.update"),
    IntentExample(id=188, text="Update the milk item to need priority", intent="shopping.update"),
    IntentExample(id=189, text="Change eggs from want to need on my list", intent="shopping.update"),

    # --- wishlist.add ---
    IntentExample(id=190, text="Add Sony headphones to my wishlist", intent="wishlist.add"),
    IntentExample(id=191, text="I'd love to get a new guitar someday", intent="wishlist.add"),
    IntentExample(id=192, text="Put the new iPhone on my wishlist", intent="wishlist.add"),
    IntentExample(id=193, text="Add a standing desk to my wish list", intent="wishlist.add"),

    # --- wishlist.list ---
    IntentExample(id=194, text="Show my wishlist", intent="wishlist.list"),
    IntentExample(id=195, text="What's on my wish list?", intent="wishlist.list"),
    IntentExample(id=196, text="List everything on my wishlist", intent="wishlist.list"),

    # --- wishlist.delete ---
    IntentExample(id=197, text="Remove the headphones from my wishlist", intent="wishlist.delete"),
    IntentExample(id=198, text="Delete the guitar from my wish list", intent="wishlist.delete"),
    IntentExample(id=199, text="Take the iPhone off my wishlist", intent="wishlist.delete"),

    # --- wishlist.promote ---
    IntentExample(id=200, text="I want to actually buy the headphones now", intent="wishlist.promote"),
    IntentExample(id=201, text="Move the guitar from my wishlist to the shopping list", intent="wishlist.promote"),
    IntentExample(id=202, text="Promote the standing desk from wishlist to shopping", intent="wishlist.promote"),

    # --- unknown ---
    IntentExample(id=141, text="What's the weather like today?", intent="unknown"),
    IntentExample(id=142, text="Tell me a joke", intent="unknown"),
    IntentExample(id=143, text="How is the stock market doing?", intent="unknown"),
    IntentExample(id=144, text="What time is it in Tokyo?", intent="unknown"),
    IntentExample(id=145, text="Translate hello to French", intent="unknown"),
    IntentExample(id=146, text="Who won the football match last night?", intent="unknown"),
    IntentExample(id=147, text="What's the capital of Brazil?", intent="unknown"),
    IntentExample(id=148, text="Play some music", intent="unknown"),
    IntentExample(id=149, text="Write a poem about autumn", intent="unknown"),
    IntentExample(id=150, text="How tall is Mount Everest?", intent="unknown"),
    IntentExample(id=151, text="Give me a recipe for pasta carbonara", intent="unknown"),
    IntentExample(id=152, text="What's the latest news?", intent="unknown"),
]

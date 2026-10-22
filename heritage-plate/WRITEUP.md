# Heritage Plate: why we built it

## The problem

When a parent is diagnosed with type 2 diabetes, high blood pressure or high cholesterol, the family gets handed generic diet advice: eat brown rice, cut salt, avoid fried food. None of it is about *their* food.

For families who cook from a tradition (aloo paratha, rajma chawal, adobo, lasagne, arroz con pollo), the advice usually means one of two things:

- **Give up the family's food** for bland "diet" meals the parent doesn't want to eat, so they quietly drift back to the old recipes, unchanged.
- **Keep cooking the same way** because no one can say how much rice, ghee or soy sauce is actually too much.

The person doing the cooking, often an adult child looking after an ageing parent, has no easy way to take Mum's real recipe, written the way she says it ("3 katori atta, ghee on top"), and work out what to change and by how much.

## What Heritage Plate does

It keeps the family's food and fixes the numbers.

1. **Read the recipe the way it's said at home.** Free text in any mix of languages and household measures (katori, spoons, "a little") becomes ingredients in grams.
2. **Adapt the dish, don't replace it.** Up to four changes that keep it recognisable: a flour mix, a smaller starch portion with more vegetables, less ghee, sugar, salt or salty sauce.
3. **Show the difference honestly.** Before-and-after nutrition per serving, focused on what matters for the condition: net carbs for diabetes, sodium for blood pressure, saturated fat for cholesterol.
4. **Plan the week.** A 7-day plan from the family's own dishes, a shopping list with quantities, and a warm note to the parent in their own language.

## What makes it trustworthy

- **The AI never makes up nutrition numbers.** Nemotron reads and adapts recipes; every number is calculated in code from published food-composition tables (IFCT 2017 for South Asian staples, USDA SR28 for the rest). Each dish shows where its numbers come from.
- **It says what it doesn't know.** Ingredients it can't match are shown as "not counted", and it won't claim a "% less" if the adapted dish adds something it can't measure.
- **Every AI result is checked.** Model replies are validated before use; a week plan that breaks the rules is replaced by a rule-based one.
- **General healthy-eating guidance, not medical advice.** The app says so and points families back to their doctor or dietitian.

## How it uses NVIDIA and Nebius

Each Nemotron tier has its own job, served from Nebius Token Factory:

| Step | Model | Why that tier |
|---|---|---|
| Read the recipe | Nemotron 3 **Nano** | Fast, structured extraction |
| Adapt each dish | Nemotron 3 **Super** | Careful, constrained rewriting |
| Plan the week and write the note | Nemotron 3 **Ultra** | Planning across all dishes plus writing in the parent's language; falls back to Super automatically |

In a live run of the full demo (4 families, 18 dishes, 5 week plans), all 24 model calls succeeded. Median response was about 1.8 s per dish and 3.6 s per week plan, Ultra never needed its fallback, and the whole run used about 29,000 tokens, a few cents.

## Who it's for

Families from any food tradition caring for a parent with a diet-related condition. It's built first for diaspora households (South Asian, East and Southeast Asian, Continental European, Middle Eastern, Latin American and Caribbean), whose food is often missing from mainstream diet apps.

**Keep the family's food. Fix the numbers.**

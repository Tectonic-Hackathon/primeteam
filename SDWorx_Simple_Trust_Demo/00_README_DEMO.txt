SD WORX SIMPLE DEMO SCENARIO
Fictional test data for the Tectonic Hackathon.

PERSON
Laura Peeters — employee of fictional client Northstar Logistics Belgium.
She starts approved 1/5 parental leave on 1 September 2026.

QUESTION A — THE SYSTEM CAN ANSWER
“Should Laura's employer-paid contractual salary be calculated at 80% or 100% during the 1/5 parental-leave period?”

EXPECTED ANSWER
80%, based on the current Belgian guide and the current Northstar client note.

WHAT THE SYSTEM SHOULD NOTICE
- Main guide says 80%, but also contains an accidentally retained old sentence saying 100%.
- Old 2022 procedure says 100%, is still marked Active by mistake, and its owner left.
- Recent Client Service email says 100%, but explicitly relies on old onboarding material.
- Netherlands document is current but does not apply to Belgium.
- Current Northstar client note and recent Payroll Operations Teams message support 80%.

Expected UI:
ANSWER: 80%
EVIDENCE: current Belgian guide + Northstar client note + Teams confirmation.
FOR REVIEW: conflicting paragraph in main guide; legacy 2022 document; Client Service email.
NOT APPLICABLE: Netherlands document.

QUESTION B — THE SYSTEM MUST NOT ANSWER
“How much public parental-leave allowance will Laura personally receive?”

EXPECTED RESPONSE
“I don't have enough verified information in the available knowledge base to answer this question. The available payroll documents explicitly do not determine the public allowance amount. I recommend asking Amélie Dubois, Belgian Benefits Specialist, who is listed as the relevant expert for public parental-leave allowance questions.”

WHY THIS MATTERS
The demo proves both sides of trust:
1. When evidence exists, resolve conflicts and show the supported answer.
2. When evidence does not exist, do not hallucinate. Say what is missing and route the user to the right expert.

IMPORTANT
All facts, companies, people and rules in this package are fictional test data. They are not legal, payroll or HR advice.

  
**VoxAgent**

Product Requirements Document

| Version | 1.0 |
| :---- | :---- |
| **Status** | Draft |
| **Product Type** | Voice AI Agent Platform |
| **Target Markets** | Coaching, Finance, Travel, Support, Sales |
| **Phase** | MVP Scoping |

# **1\. Product Vision**

VoxAgent is a developer-friendly voice AI platform that enables companies to deploy intelligent phone agents. Unlike traditional IVR systems, VoxAgent agents understand natural language and adapt responses dynamically.

| Core Promise A fully configurable voice agent platform that answers inbound calls, makes outbound calls, accesses company knowledge, performs actions, and transfers to human agents when necessary. |
| :---- |

**Agent Capabilities**

* Answer inbound calls intelligently

* Make outbound calls at scale

* Access and retrieve company knowledge in real time

* Perform actions: book meetings, update CRM, send messages

* Transfer to human agents when the conversation demands it

# **2\. Core Use Cases**

VoxAgent targets five primary verticals in its MVP launch:

| Vertical | Primary Use Case |
| :---- | :---- |
| **Coaching Institutes** | Lead qualification via automated inbound/outbound calls |
| **Finance** | Loan collection reminders and payment follow-ups |
| **Healthcare / Services** | Appointment booking and rescheduling |
| **Customer Support** | Tier-1 support handling with human escalation |
| **Sales Teams** | Automated follow-up calls and lead nurturing |

# **3\. Target Users**

| Business Owner | Operations Manager | Developer |
| ----- | ----- | ----- |
| Wants automated call handling with minimal setup. Focused on outcomes and cost savings. | Monitors call performance and agent health. Needs real-time dashboards and clear metrics. | Configures agents, integrations, and conversation logic. Needs APIs, debugger, and workflow tools. |

# **4\. Key Product Features**

## **4.1 Voice Agent Builder**

Users configure agents through a visual interface without writing raw prompts.

* Agent name, voice, and language selection

* Knowledge base connection

* Skill toggles (meeting booking, CRM update, transfer)

* Behavior and conversation style rules

* Agent persona definition

## **4.2 Knowledge Base**

The knowledge base is the core intelligence layer for each agent.

* Supported input formats: PDF, FAQ text, website URLs, documents

* Automatic conversion to embeddings and storage in a vector database

* RAG (Retrieval-Augmented Generation) used for real-time knowledge retrieval during calls

* Embedding status tracking and last-update visibility

## **4.3 Agent Skills**

Agents can be equipped with action skills that trigger during conversations:

* Schedule meetings

* Send SMS or email

* Update CRM records

* Transfer call to a human agent

## **4.4 Call Management**

Full visibility into both inbound and outbound call activity.

* Inbound call handling and routing

* Outbound campaign management (CSV upload)

* Call recording, transcripts, and summaries

* Call outcomes and disposition tracking

## **4.5 Conversation Logic**

Configurable conversation behavior for edge cases and handoffs:

* Intent detection and classification

* State tracking across turns

* Fallback responses for low-confidence scenarios

* Human transfer triggers and conditions

* Silence and no-input handling

## **4.6 Dashboard Analytics**

Key metrics visible at a glance:

* Calls answered and resolution rate

* Conversion rate and lead capture

* Average call duration

* Call sentiment distribution

* Agent performance comparison

# **5\. System Architecture**

The call pipeline processes voice end-to-end through a modular chain:

| Processing Pipeline Each inbound or outbound call passes through the full pipeline sequentially. Components are independently swappable. |
| :---- |

**Telephony (Twilio)**  \--\>  **Speech-to-Text (Sarvam)**  \--\>  **Intent Router (LLM)**  \--\>  **Conversation Manager**

**Knowledge Retrieval (Vector DB)**  \--\>  **Reasoning LLM (Gemini Flash)**  \--\>  **Tool Execution**  \--\>  **Text-to-Speech (Sarvam)**

Each layer is independently swappable. The intent router uses a small, fast LLM to classify user intent before invoking the heavier reasoning model, keeping latency low.

## **5.1 Conversation State Manager**

During a live call, the agent must remember context across multiple turns: what was said, which intents were detected, what actions were taken, and what still needs to happen. This context is the conversation state. It must be fast to read and write on every turn, and it must be fully persisted to the database when the call ends.

**Where State Lives**

While a call is active, state lives entirely in Redis. Redis is chosen because it is in-memory, gives sub-millisecond read/write latency, and supports TTL-based automatic expiry for abandoned sessions. Each session is stored under a structured key:

| Redis Session Key Pattern call\_session:{call\_id} Example:  call\_session:abc123 |
| :---- |

**What the Session Object Contains**

| Field | Description |
| :---- | :---- |
| **call\_id** | Unique call identifier, also used as the Redis key suffix |
| **agent\_id** | Which agent is handling this call |
| **current\_intent** | Last detected intent from the intent router |
| **conversation\_history** | Running list of turns (role \+ text) passed to the reasoning LLM |
| **collected\_data** | Structured data gathered so far (name, interest level, meeting time, etc.) |
| **tools\_executed** | Log of skills triggered during this call (e.g., meeting booked, CRM updated) |
| **call\_status** | Current status: active, transferring, or ending |
| **ttl** | Redis TTL (e.g. 30 minutes). Automatically expires orphaned sessions if a call drops unexpectedly. |

**State Lifecycle**

| Phase | Storage | Action |
| :---- | :---- | :---- |
| **Call starts** | Redis | Create session object at call\_session:{call\_id} with TTL |
| **Each turn** | Redis (read \+ write) | Read current state, update intent \+ history \+ collected\_data, write back |
| **Skill triggered** | Redis \+ external service | Append to tools\_executed in session; call external API (calendar, CRM) |
| **Call ends** | Redis then Supabase (DB) | Flush final state to Supabase (lead record \+ call summary); delete Redis key |
| **Call dropped** | Redis TTL auto-expires | Webhook from Twilio triggers a cleanup job that flushes partial state before expiry |

This two-tier model (Redis for hot state, Supabase for durable records) is already reflected in the technology stack in Section 6\. Section 5.1 formalizes how those two layers interact during a call.

# **6\. Technology Stack**

| Backend | Python FastAPI |
| :---- | :---- |
| **Dashboard (Frontend)** | Next.js |
| **Telephony** | Twilio |
| **Speech (STT \+ TTS)** | Sarvam |
| **Primary LLM** | Gemini Flash |
| **Intent Router** | Small LLM (low latency) |
| **Vector Database** | Supabase |
| **Session Memory** | Redis |
| **Deployment** | Railway / VPS |

# **7\. Data Model**

A representative lead record captures the key data points generated per call:

| Field | Type | Description |
| :---- | :---- | :---- |
| **lead\_id** | UUID | Unique lead identifier |
| **phone** | String | Lead phone number |
| **name** | String | Lead full name |
| **email** | String | Lead email address |
| **interest\_level** | Enum | Low / Medium / High |
| **meeting\_time** | Datetime | Scheduled meeting slot |
| **call\_summary** | Text | Auto-generated call summary |
| **agent\_id** | UUID | Assigned agent reference |
| **company\_id** | UUID | Company tenant reference |

# **8\. Security Requirements**

* Call data encryption in transit and at rest

* Company data isolation per tenant (multi-tenancy)

* API key authentication for all integrations

* Role-based access control (Owner, Manager, Developer)

# **9\. MVP Scope (Phase 1\)**

The following features are in scope for the initial launch:

| Phase 1 Deliverables Agent Builder, Knowledge Base, Live Voice Calls, Meeting Scheduling, Human Transfer, Analytics Dashboard. |
| :---- |

| In Scope (Phase 1\) | Future Phases |
| :---- | :---- |
| Agent builder and persona config Knowledge base with RAG Inbound and outbound voice calls Meeting scheduling skill Human transfer skill Core analytics dashboard | Advanced workflow canvas builder SMS and email skill integrations CRM integration (HubSpot, Salesforce) Advanced campaign manager Conversation debugger Multi-language expansion |

# **10\. UI/UX Design Philosophy**

VoxAgent should feel like a call center operating system, not an AI toy dashboard. Design inspiration: Linear, Vercel, Stripe.

| Avoid ChatGPT-clone chat interfaces Generic AI prompt box UIs Cluttered sidebar navigation Excessive color and AI-startup cliches | Use Instead Visual workflow builders Operational dashboards Agent control panels Dark \+ neutral palette, large typography |
| :---- | :---- |

## **10.1 Navigation Structure**

Left sidebar navigation with seven primary sections:

* Dashboard (Home) with key metrics and charts

* Agents with agent builder and management

* Calls with real-time monitoring and transcript viewer

* Knowledge Base with document manager

* Campaigns for outbound campaign management

* Analytics for deep performance analysis

* Settings for account and integration configuration

## **10.2 Key Pages**

**Agent Builder**

Main product page. Visual blocks for persona, conversation rules, and tools. Voice and language selectors. Skill toggle panel.

**Workflow Builder**

Graph-based canvas (inspired by Voiceflow / Retell AI). Nodes for: Start Call, Greeting, Intent Detection, Knowledge Search, Action, Close Call. Eliminates prompt-engineering confusion for non-technical users.

**Call Monitoring**

Real-time table view with columns: Phone, Agent, Status, Duration, Sentiment, Outcome. Click any row to open full transcript.

**Conversation Debugger**

Pipeline visibility for developers: Speech Input, Intent Detection Result, Knowledge Retrieval Result, LLM Response, Tool Execution output. Critical for debugging agent behavior.

**Campaign Manager**

Upload a CSV with phone, name, and notes columns. Configure agent and launch outbound campaign. Track delivery and outcomes per contact.

*Document End*
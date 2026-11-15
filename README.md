## Inspiration
Prior authorization is the single biggest non-cost burden in U.S. healthcare for insured adults. On the side of careproviders, 95% of physicians report that prior authorization delays access to necessary care, with 13 hours a week on average spent handling these requests by the average physician. On the side of patients, 34% of insured adults name prior authorization as the single biggest burden of getting health care. 

Unburden seeks to reduce this burden for all parties involved (careproviders, patients, and insurance providers) in a simple, explainable, and accessible way. Any patient, whether they have a disability, technical limitation, or are elderly patients, can receive the care they need with the click of a button and a single FaceTime call. That's Unburden.

## What it does
Unburden bridges the gap between the patient and the careprovider. Patients upload any and all relevant medical documents through a simple FaceTime call with an AI agent, which uploads the PDF detected into the patient's database. 

Unburden automatically parses all of these documents and stores it into that patient's database. From there, these documents are automatically classified into different sections based on the specific insurance requirements they satisfy. From there, all the careprovider needs to do is manually review that this information is correct and satisfactory. If any documents are unsatisfactory or missing, they only need to click one button to send an AI agent to FaceTime call the patient, requesting a specific document. 

Once every condition is satisfied, the careprovider can simply export all the documents into bundled prior authorization request, ready to send to their insurance provider. 

## How we built it
### Document upload with Chert
When an agent calls a patient, a LiveKit session is created. This dispatches a Chert AI voice agent to call the patient, which extracts the PDF from the video and uploads it to the Unburden database for that patient.

### PDF parsing with PyMuPDF
For regularly uploaded pdfs, PyMuPDF extracts all of the text from them. However, with uploaded photos (including FaceTime pictures), this library doesn't work. Instead, we combined PyMuPDF with Tesseract OCR to parse these more complicated photos. Because this had a couple of typos, this is cleaned up with post-OCR text normalization to make it ready for NLP tasks. 

### Insurance requirement matching with DeBERTa NLI
This is where the bulk of the project's technical depth is, in my opinion. Once documents are in the patient record, Unburden evaluates them against a structured insurance policy. Each requirement is encoded with retrieval terms, acceptable document types, temporal windows, numeric thresholds, and phrase-level accept/reject rules.

To figure out whether a passage actually supports an insurance requirement, we use a DeBERTa-v3 NLI model. It takes the extracted passage and the requirement as a premise. We calibrated the decision thresholds on TREC clinical-trials data instead of fine-tuning weights, and structured checks (dates, numbers, document types, quote-in-source) still decide what gets accepted the. Tldr: We combined an open source zero-shot NLP model (DeBERTa) with M3 (my personal name for milestone 3, which are structured checks), and calibrated this on real clinical trial data that only some parts of DeBERTa captures.

This outputs 3 probabilities (after applying Softmax): support, insufficient, contradiction that should sum to 100%. For the sake of explainability, our simple "match" probability is simply support - contradiction. 

## Challenges we ran into
Getting Chert + FaceTime stable: Configurations were unstable at some times, and we had to configure the agent to do and say the right thing.

FaceTime video text extraction: The blurry quality and photo tendencies of FaceTime captures required us to look beyond simple PyMuPDF to extract production-ready text extractions.

Matching model: To match documents to insurance requirements, many models were built, tested, and benchmarked. (and scrapped...)

## Accomplishments that we're proud of
In the end, despite all of the various components, the application turned out successful and ultimately simple, which was our goal. While a lot of components are technically running in the backend, the UI is incredibly explainable and easy to navigate. 

## What we learned
The use of a WIDE variety of different tools, including those that will be listed below. And of course, greater knowledge of the medical industry and the growing challenges in the healthtech world. 

## What's next for Unburden
So much potential is out there! Obviously, our text extraction model and DeBERTa model can be improved (maybe building and training our own NLI model, rather than still using a zero-shot open source model that isn't even specific to medical information...)

## SpaceXSI: How we used Cursor and GrokBot
Cursor was IDE of choice for this project. Usually I will pull up Codex and connect it to base VSCode, but in this hackathon, there were so many different tools and agents to manage. Cursor helped me simplify this and allowed me to easily view the changes that were taking place, while also being incredible for rapidly testing and iterating on my ideas. (fun fact, at the beginning of the hackathon, Cursor was incredibly slow on my laptop and eating up 100% of my CPU usage. The solution was to downgrade the version by one, which worked by some miracle).

On the other hand, GrokBot served as the UI/UX engineer on my team that I didn't have. Being a solo hacker, it was difficult to manage both iteration of new features alongside bug fixes that I didn't have time to catch and hunt for myself in the frontend. In this hackathon, I was able to leverage my own "Frontend Guidelines Bot" with GrokBot, which I gave specific instructions for what I wanted it to do after each GitHub commit. Based on my frontend requirements, it would automatically navigate the user interface and take pictures, give suggestions, and fix bugs on all accessibility methods (iPhone view and desktop view). From there, it would bundle these changes into a pull request on GitHub for me to review, which was great, because I didn't need it to automatically make changes while I was still building! Once I was working on a frontend feature, that's when I made a lot of merges from GrokBot's suggestions.

## Coder: How we used the Coder environment
Coder made it frictionless to set up all of my agents, IDEs, and workflows with minimal stress. I used it to create my environment and add in everything I needed in one place (GitHub, Cursor, and AI Agents). But where Coder helped the most was the ease of spinning off subagents. Because Coder had access to all of the information, code, and context in my repository, I could send off Sonnet subagents to do anything while my development was taking place, without eating up context on the development side. I was able to use chat with Sonnet in Coder for UI ideas, logo design, and most importantly background research tasks as I tried to compare and contrast models for my inference and classification tasks. 

## Entire: How we leveraged Entire
Unburden was built across ~7 Cursor chats, with milestones, compaction, new agents starting cold. Without shared memory, each one would’ve re-derived (or undone) the last.

Sessions checkpointed Cursor turns into git so work survived dead chats. I actually saw the real impact of Brain: after compaction or switching agents, Cursor recalled durable decisions (Chert intake, OCR fallback, DeBERTa gating, status vocabulary) instead of guessing. Graph kept edits targeted, while Trails reviewed and merged.

As my first time using Entire, I was pretty amazed with its features that it came with during this weekend. Most importantly, once I installed it, I didn't really have to do much and it still ran in the backend with its features. A couple screenshots are included in our media gallery that display some features I was very impressed with. 
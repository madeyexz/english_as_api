## English as API

> *The new API is English.*

The goal is to make Anthropic's [Computer Use](https://www.anthropic.com/news/3-5-models-and-computer-use) more capable and robust.

### The Problem

I was playing with Computer Use the day it came out, it felt like an interesting toy. I mirrored my iPhone to my Mac and tried to let Computer Use control my phone via the macOS interface. I noticed that it needed additional prompting to make it control my phone.

Then I tried to let it control my Mac. I prompted it to work with my Reader app and search for a specific article. It failed because it didn't know how to use the Reader app.

So I thought, **why not just feed the context of the web apps to the model so that it can knows where and how to do stuffs?**

### Potential Solutions

There are several approaches to make Computer Use more capable, I will focus on the second one.

1. **Documentation-Based Context**
   - Create comprehensive documentation that outlines the web app's functionality, including detailed step-by-step guides for common tasks, clear definitions of interactive elements, and mapped user flows with expected outcomes. (yeah i want this automated)

2. **Dynamic Analysis**
   - Automatically analyze the web app's interface to build a semantic understanding of UI elements, their relationships and functions, creating an indexed map that can be fed to the model as structured contextual information. (mmhmm pretty reasonable)

3. **Autonomous Agent Approach**
   - Develop an autonomous agent system that explores and learns interfaces through trial and error, leveraging reinforcement learning to optimize interactions while building and maintaining a knowledge base of successful patterns. (too complicated)


### Current Implementation

The current implementation focuses on the Dynamic Analysis approach. It consists of:

1. A semantic parser that analyzes web pages to understand:
   - Page structure and hierarchy
   - Interactive elements (buttons, forms, links)
   - Navigation patterns
   - Content sections and their purposes
   - Available actions and tasks

2. JSON output that provides:
   - Structured representation of the page
   - Mapped user interface elements
   - Possible interactions and their contexts
   - Semantic relationships between elements

The goal is to feed this structured understanding to Claude to enable more informed interactions with web interfaces.

### Next Steps

1. Improve semantic parsing accuracy
2. Add support for dynamic content analysis
3. Implement better action inference
4. Create a standardized format for context sharing
5. Test with various web applications
6. Integrate with Claude's Computer Use capability

### Installation

1. Create a virtual environment:

```bash
uv venv
```

2. Install dependencies:

```bash
uv pip install -r requirements.txt
```

3. Set the `URL` variable in `webpage_semantic_parser.py` to the URL of the webpage you want to analyze, then run the script:

```bash
python webpage_semantic_parser.py
```
4. Results will be saved in `understanding.json` and `index_tree.json`.

### Contributing

Feel free to open issues or submit PRs to help improve the implementation.


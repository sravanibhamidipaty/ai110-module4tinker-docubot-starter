"""
Core DocuBot class responsible for:
- Loading documents from the docs/ folder
- Building a simple retrieval index (Phase 1)
- Retrieving relevant snippets (Phase 1)
- Supporting retrieval only answers
- Supporting RAG answers when paired with Gemini (Phase 2)
"""

import os
import glob
import re
from collections import Counter


class DocuBot:
    def __init__(self, docs_folder="docs", llm_client=None):
        """
        docs_folder: directory containing project documentation files
        llm_client: optional Gemini client for LLM based answers
        """
        self.docs_folder = docs_folder
        self.llm_client = llm_client

        # Load documents into memory
        self.documents = self.load_documents()  # List of (filename, text)
        self.sections = self.build_sections(
            self.documents)  # List of (source, text)

        # Build a retrieval index (implemented in Phase 1)
        self.index = self.build_index(self.sections)

        # Guardrail thresholds for deciding whether evidence is strong enough.
        self.min_section_score = 1
        self.stopwords = {
            "a", "an", "and", "are", "as", "at", "be", "by", "do", "for",
            "from", "how", "i", "if", "in", "is", "it", "its", "me", "my",
            "now", "of", "on", "or", "that", "the", "this", "to", "was",
            "we", "what", "when", "where", "which", "with", "you", "your",
            "time", "maybe"
        }

    # -----------------------------------------------------------
    # Document Loading
    # -----------------------------------------------------------

    def load_documents(self):
        """
        Loads all .md and .txt files inside docs_folder.
        Returns a list of tuples: (filename, text)
        """
        docs = []
        pattern = os.path.join(self.docs_folder, "*.*")
        for path in glob.glob(pattern):
            if path.endswith(".md") or path.endswith(".txt"):
                with open(path, "r", encoding="utf8") as f:
                    text = f.read()
                filename = os.path.basename(path)
                docs.append((filename, text))
        return docs

    # -----------------------------------------------------------
    # Sectioning for Fine-Grained Retrieval
    # -----------------------------------------------------------

    def split_into_sections(self, text):
        """
        Split a document into paragraph-like sections.

        Rule:
        - Primary split on one or more blank lines
        - Trim whitespace
        - Drop empty chunks
        """
        raw_sections = re.split(r"\n\s*\n+", text)
        return [section.strip() for section in raw_sections if section.strip()]

    def build_sections(self, documents):
        """
        Build retrieval units from full documents.

        Returns a list of tuples: (source_label, section_text)
        where source_label looks like: "AUTH.md (section 2)".
        """
        sections = []
        for filename, text in documents:
            doc_sections = self.split_into_sections(text)

            # Fallback so every file contributes at least one retrieval unit.
            if not doc_sections:
                doc_sections = [text.strip()] if text.strip() else []

            for i, section_text in enumerate(doc_sections, start=1):
                source_label = f"{filename} (section {i})"
                sections.append((source_label, section_text))

        return sections

    # -----------------------------------------------------------
    # Index Construction (Phase 1)
    # -----------------------------------------------------------

    def build_index(self, sections):
        """
        TODO (Phase 1):
        Build a tiny inverted index mapping lowercase words to section labels
        they appear in.

        Example structure:
        {
            "token": ["AUTH.md (section 1)", "API_REFERENCE.md (section 2)"],
            "database": ["DATABASE.md (section 3)"]
        }

        Keep this simple: split on whitespace, lowercase tokens,
        ignore punctuation if needed.
        """
        index = {}

        # Step 1: Iterate through each section
        for source_label, text in sections:
            # Step 2: Tokenize section text
            words = self.tokenize_text(text)

            # Step 3: Add each token to the index
            for token in words:
                if token:
                    # Step 4: Add filename to index entry if not already there
                    if token not in index:
                        index[token] = []

                    # Avoid duplicates in the section list
                    if source_label not in index[token]:
                        index[token].append(source_label)

        return index

    # -----------------------------------------------------------
    # Scoring and Retrieval (Phase 1)
    # -----------------------------------------------------------

    def normalize_token(self, token):
        """
        Apply lightweight normalization so simple plural/singular forms align.
        """
        if len(token) > 3 and token.endswith("s"):
            return token[:-1]
        return token

    def tokenize_text(self, text):
        """
        Convert raw text into normalized lowercase word tokens.
        """
        raw_tokens = re.findall(r"[a-z0-9_]+", text.lower())
        return [self.normalize_token(token) for token in raw_tokens]

    def score_document(self, query, text):
        """
        Return a simple relevance score for how well the text matches the query.

        This score uses exact token frequency matches (not substring matches),
        which avoids false positives like matching "me" inside unrelated words.
        """
        query_tokens = self.extract_query_tokens(query)
        if not query_tokens:
            return 0

        text_counts = Counter(self.tokenize_text(text))

        score = 0
        for token in query_tokens:
            score += text_counts[token]

        return score

    def extract_query_tokens(self, query):
        """
        Normalize query into deduplicated content tokens for evidence checks.
        """
        tokens = []
        for token in self.tokenize_text(query):
            if token and token not in self.stopwords:
                tokens.append(token)
        return sorted(set(tokens))

    def count_query_token_overlap(self, query_tokens, text):
        """
        Count how many distinct query tokens appear in a candidate section.
        """
        if not query_tokens:
            return 0

        section_tokens = set(self.tokenize_text(text))
        return sum(1 for token in query_tokens if token in section_tokens)

    def has_meaningful_evidence(self, query, scored_sections):
        """
        Decide whether retrieved context is strong enough to answer.

        We require:
        - at least one scored section
        - the best section score to pass a minimum threshold
        - overlap with enough distinct query terms
        """
        if not scored_sections:
            return False

        query_tokens = self.extract_query_tokens(query)
        if not query_tokens:
            return False

        required_overlap = 1 if len(query_tokens) == 1 else 2

        for _, section_text, section_score in scored_sections:
            if section_score < self.min_section_score:
                continue

            overlap = self.count_query_token_overlap(
                query_tokens, section_text)
            if overlap >= required_overlap:
                return True

        return False

    def retrieve_with_scores(self, query, top_k=3):
        """
        Return top sections as (source_label, text, score) tuples.
        """
        # Step 1: Create a dict to store scores for each section
        section_scores = {}

        # Step 2: Score each section
        for source_label, text in self.sections:
            score = self.score_document(query, text)
            if score > 0:
                section_scores[source_label] = score

        # Step 3: Sort by score descending
        sorted_sections = sorted(
            section_scores.items(),
            key=lambda x: x[1],
            reverse=True,
        )

        # Step 4: Build results list with (source_label, text, score) tuples
        results = []
        for source_label, score in sorted_sections[:top_k]:
            # Find the section text
            for section_source, section_text in self.sections:
                if section_source == source_label:
                    results.append((source_label, section_text, score))
                    break

        return results

    def retrieve(self, query, top_k=3):
        """
        TODO (Phase 1):
        Use the index and scoring function to select top_k relevant document snippets.

        Return a list of (source_label, text) sorted by score descending.
        """
        scored_sections = self.retrieve_with_scores(query, top_k=top_k)
        return [(source_label, text) for source_label, text, _ in scored_sections]

    # -----------------------------------------------------------
    # Answering Modes
    # -----------------------------------------------------------

    def answer_retrieval_only(self, query, top_k=3):
        """
        Phase 1 retrieval only mode.
        Returns raw snippets and filenames with no LLM involved.
        """
        scored_snippets = self.retrieve_with_scores(query, top_k=top_k)

        if not self.has_meaningful_evidence(query, scored_snippets):
            return "I do not know based on these docs."

        snippets = [(source_label, text)
                    for source_label, text, _ in scored_snippets]

        formatted = []
        for filename, text in snippets:
            formatted.append(f"[{filename}]\n{text}\n")

        return "\n---\n".join(formatted)

    def answer_rag(self, query, top_k=3):
        """
        Phase 2 RAG mode.
        Uses student retrieval to select snippets, then asks Gemini
        to generate an answer using only those snippets.
        """
        if self.llm_client is None:
            raise RuntimeError(
                "RAG mode requires an LLM client. Provide a GeminiClient instance."
            )

        scored_snippets = self.retrieve_with_scores(query, top_k=top_k)

        if not self.has_meaningful_evidence(query, scored_snippets):
            return "I do not know based on these docs."

        snippets = [(source_label, text)
                    for source_label, text, _ in scored_snippets]

        return self.llm_client.answer_from_snippets(query, snippets)

    # -----------------------------------------------------------
    # Bonus Helper: concatenated docs for naive generation mode
    # -----------------------------------------------------------

    def full_corpus_text(self):
        """
        Returns all documents concatenated into a single string.
        This is used in Phase 0 for naive 'generation only' baselines.
        """
        return "\n\n".join(text for _, text in self.documents)

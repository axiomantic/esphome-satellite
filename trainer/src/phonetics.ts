/**
 * Phonetic Normalizer and Validator for On-Device Wake Word Models.
 * Ensures input text translates cleanly to acoustic speech phonemes.
 */

const DIGIT_WORDS: Record<string, string> = {
  "0": "zero",
  "1": "one",
  "2": "two",
  "3": "three",
  "4": "four",
  "5": "five",
  "6": "six",
  "7": "seven",
  "8": "eight",
  "9": "nine",
  "10": "ten",
};

const LETTER_NAMES: Record<string, string> = {
  a: "ay",
  b: "bee",
  c: "see",
  d: "dee",
  e: "ee",
  f: "ef",
  g: "jee",
  h: "aych",
  i: "eye",
  j: "jay",
  k: "kay",
  l: "el",
  m: "em",
  n: "en",
  o: "oh",
  p: "pee",
  q: "cue",
  r: "ar",
  s: "ess",
  t: "tee",
  u: "you",
  v: "vee",
  w: "double you",
  x: "ex",
  y: "why",
  z: "zee",
};

const COMMON_EXPANSIONS: Record<string, string> = {
  ok: "okay",
  dj: "dee jay",
  pj: "pee jay",
  ai: "ay eye",
  tv: "tee vee",
  pc: "pee see",
  id: "eye dee",
  c3p0: "see three pee oh",
  r2d2: "ar two dee two",
  bb8: "bee bee eight",
};

/**
 * Expands digit strings into spoken word representations.
 */
export function expandNumbers(text: string): string {
  return text.replace(/\b(\d+)\b/g, (match) => {
    if (DIGIT_WORDS[match]) {
      return DIGIT_WORDS[match];
    }
    return match
      .split("")
      .map((d) => DIGIT_WORDS[d] || d)
      .join(" ");
  });
}

/**
 * Expands alphanumeric acronyms like "c3p0" -> "see three pee oh".
 */
export function expandAlphanumeric(text: string): string {
  return text
    .split(/\s+/)
    .map((word) => {
      const lower = word.toLowerCase();
      if (COMMON_EXPANSIONS[lower]) {
        return COMMON_EXPANSIONS[lower];
      }

      // If word mixes letters and numbers (e.g. c3p0, r2d2)
      if (/[a-z]/.test(lower) && /\d/.test(lower)) {
        return lower
          .split("")
          .map((char) => {
            if (DIGIT_WORDS[char]) {
              // Special case: 0 in droid names often pronounced "oh"
              return char === "0" ? "oh" : DIGIT_WORDS[char];
            }
            if (LETTER_NAMES[char]) {
              return LETTER_NAMES[char];
            }
            return char;
          })
          .join(" ");
      }

      // If word is a short acronym in all caps or known initialism (e.g. DJ, PJ)
      if (/^[a-z]{2,3}$/.test(lower) && !["the", "and", "for", "are", "you", "hey", "yes"].includes(lower)) {
        if (COMMON_EXPANSIONS[lower]) return COMMON_EXPANSIONS[lower];
      }

      return word;
    })
    .join(" ");
}

/**
 * Normalizes a raw phrase into its full phonetic text equivalent.
 * Example: "ok c3p0" -> "okay see three pee oh"
 * Example: "dj pj" -> "dee jay pee jay"
 */
export function normalizePhoneticPhrase(phrase: string): string {
  let cleaned = phrase
    .toLowerCase()
    .replace(/[^\w\s]/g, " ")
    .replace(/\s+/g, " ")
    .trim();

  cleaned = expandAlphanumeric(cleaned);
  cleaned = expandNumbers(cleaned);

  // Clean any remaining punctuation or extra spaces
  return cleaned
    .replace(/[^\w\s]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

export interface PhoneticValidationResult {
  isValid: boolean;
  normalized: string;
  suggestions: string[];
}

/**
 * Analyzes whether an input phrase is properly spelled phonetically or if it needs expansion.
 */
export function validatePhoneticSpelling(phrase: string): PhoneticValidationResult {
  const suggestions: string[] = [];
  const trimmed = phrase.trim();
  const normalized = normalizePhoneticPhrase(trimmed);

  if (!trimmed) {
    return {
      isValid: false,
      normalized: "",
      suggestions: ["Phrase cannot be empty."],
    };
  }

  if (/\d/.test(trimmed)) {
    suggestions.push(
      `Digits detected: spell out numbers phonetically (e.g. "3" -> "three", "0" -> "oh" or "zero").`
    );
  }

  if (/\b(ok|dj|pj|tv|ai|pc)\b/i.test(trimmed)) {
    suggestions.push(
      `Shorthand/acronym detected: spell phonetically (e.g. "ok" -> "okay", "dj pj" -> "dee jay pee jay").`
    );
  }

  const isValid = suggestions.length === 0 && trimmed.toLowerCase() === normalized;

  return {
    isValid,
    normalized,
    suggestions,
  };
}

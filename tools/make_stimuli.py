"""Builds stimuli.js and tools/clips.tsv from the name lists below.

    python tools/make_stimuli.py

45 contact triples in 3 sets of 15. Each set holds 8 confusable triples and 7
distinct ones. In each set 3 triples (2 confusable, 1 distinct) are "absent"
trials: the requested contact is a foil that is NOT among the three options, so
the right answer is "none of these".
"""
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Names sound alike within a triple: the case a speech recogniser really gets wrong.
CONFUSABLE = [
    ("Riya Shah", "Rina Rao", "Priya Sharma"),
    ("Anita Rao", "Anika Rai", "Amita Roy"),
    ("Karan Mehta", "Kiran Mehra", "Kunal Mehta"),
    ("Neha Jain", "Neha Jha", "Nisha Jain"),
    ("Rohan Das", "Rohit Dass", "Mohan Das"),
    ("Sneha Iyer", "Sheela Iyer", "Shreya Ayyar"),
    ("Arjun Nair", "Arun Nayar", "Varun Nair"),
    ("Meera Joshi", "Meena Joshi", "Veena Joshi"),
    ("Vikram Singh", "Vikrant Sinha", "Vikas Singh"),
    ("Pooja Gupta", "Puja Gupte", "Pallavi Gupta"),
    ("Aman Verma", "Amar Varma", "Naman Verma"),
    ("Divya Menon", "Diya Menon", "Dhanya Menon"),
    ("Sanjay Patel", "Sanjiv Patil", "Ranjit Patel"),
    ("Kavya Reddy", "Kavita Reddy", "Kamya Reddi"),
    ("Tarun Bose", "Tarun Basu", "Karun Bose"),
    ("Nikhil Kapoor", "Nitin Kapur", "Nikita Kapoor"),
    ("Asha Pillai", "Usha Pillai", "Isha Pillay"),
    ("Harish Kumar", "Girish Kumar", "Harsh Kumar"),
    ("Ritu Malhotra", "Rita Malhotra", "Ruchi Mehrotra"),
    ("Deepak Sen", "Dipti Sen", "Deepa Sen"),
    ("Manish Ghosh", "Manoj Ghosh", "Manas Ghose"),
    ("Lata Desai", "Latha Deshpande", "Lalita Desai"),
    ("Gaurav Yadav", "Saurabh Yadav", "Sourav Jadhav"),
    ("Ayesha Khan", "Aisha Khanna", "Alisha Khan"),
]

# Names share no obvious sounds within a triple.
DISTINCT = [
    ("Farah Ali", "Joseph Thomas", "Bhavna Trivedi"),
    ("Mohit Chawla", "Sunita Bhatt", "Elena Fernandes"),
    ("Tanvi Kulkarni", "Imran Sheikh", "George Mathew"),
    ("Yash Agarwal", "Nandini Rawat", "Peter Dsouza"),
    ("Zoya Mirza", "Dinesh Tiwari", "Grace Lobo"),
    ("Abhay Saxena", "Lakshmi Naidu", "Jatin Sodhi"),
    ("Chetan Rathore", "Maya Fonseca", "Sahil Bedi"),
    ("Bharat Pandey", "Ishita Dutta", "Omar Qureshi"),
    ("Nora Sequeira", "Hemant Dubey", "Tara Chauhan"),
    ("Uday Bhandari", "Sofia Rodrigues", "Pankaj Mishra"),
    ("Jaya Hegde", "Kabir Bajaj", "Rekha Thakur"),
    ("Vivek Shukla", "Zara Merchant", "Gopal Krishnan"),
    ("Parul Sethi", "Dev Banerjee", "Fatima Ansari"),
    ("Ashok Tandon", "Mira Vaz", "Yusuf Lokhande"),
    ("Hina Bhalla", "Ravi Shetty", "Clara Pinto"),
    ("Suresh Goyal", "Bina Chopra", "Nasir Hussain"),
    ("Tina Arora", "Vinod Prasad", "Jaspreet Gill"),
    ("Mukesh Bansal", "Sara Abraham", "Devika Kamath"),
    ("Alok Mathur", "Rani Dhillon", "Felix Correa"),
    ("Kusum Rastogi", "Bilal Siddiqui", "Trisha Paul"),
    ("Naveen Ahuja", "Gita Oberoi", "Rafael Dias"),
]

# Requested contact on the absent trials: confusable with its triple where the triple is.
FOILS_CONFUSABLE = ["Siya Shah", "Anjali Rao", "Kiran Mehta", "Neha Jaiswal", "Rohan Dass", "Sheena Iyer"]
FOILS_DISTINCT = ["Lalit Verghese", "Maria Noronha", "Shankar Ghatge"]

PRACTICE = [
    ("Pranav Lal", "Simran Kaur", "Anil Thapa"),
    ("Shalini Jha", "Mahesh Rane", "Ruby Lewis"),
    ("Bhuvan Sood", "Bhuvana Sood", "Ramesh Sood"),
]

FIXED = {  # clip id -> (voice, text)
    "a_which": ("assistant", "Which one?"),
    "a_one": ("assistant", "One."),
    "a_two": ("assistant", "Two."),
    "a_three": ("assistant", "Three."),
    "a_correct": ("assistant", "Correct."),
    "a_wrong": ("assistant", "Not that one."),
    "a_none_right": ("assistant", "Correct. None of these."),
    "a_none_wrong": ("assistant", "It was none of these."),
}


def slug(name):
    return re.sub(r"[^a-z]+", "_", name.lower()).strip("_")


def main():
    sets = [[], [], []]
    for kind, triples, foils, n_absent in (("confusable", CONFUSABLE, FOILS_CONFUSABLE, 2),
                                           ("distinct", DISTINCT, FOILS_DISTINCT, 1)):
        counts = [0, 0, 0]
        for i, triple in enumerate(triples):
            s = i % 3
            item = {"id": f"{kind[0]}{i + 1:02d}", "similarity": kind, "names": list(triple), "foil": None}
            if counts[s] < n_absent:
                item["foil"] = foils.pop(0)
                counts[s] += 1
            sets[s].append(item)
    assert not FOILS_CONFUSABLE and not FOILS_DISTINCT
    for s in sets:
        assert len(s) == 15
        assert sum(i["similarity"] == "confusable" for i in s) == 8
        assert sum(i["foil"] is not None for i in s) == 3

    names = [n for s in sets for i in s for n in i["names"]] + [n for t in PRACTICE for n in t]
    foils = [i["foil"] for s in sets for i in s if i["foil"]]
    dupes = sorted({n for n in names if names.count(n) > 1})
    assert not dupes, dupes
    assert not set(foils) & set(names), set(foils) & set(names)

    with open(os.path.join(ROOT, "stimuli.js"), "w", encoding="utf-8", newline="\n") as f:
        f.write("// Generated by tools/make_stimuli.py. Edit the lists there, not here.\n")
        f.write("(function (root) {\n  var STIMULI = ")
        f.write(json.dumps({"sets": sets, "practice": [list(t) for t in PRACTICE]}, indent=1))
        f.write(";\n  if (typeof module !== 'undefined' && module.exports) module.exports = STIMULI;\n")
        f.write("  root.STIMULI = STIMULI;\n})(typeof self !== 'undefined' ? self : this);\n")

    # Every name can be an option (assistant voice) and a request (task voice).
    with open(os.path.join(ROOT, "tools", "clips.tsv"), "w", encoding="utf-8", newline="\n") as f:
        for cid, (voice, text) in FIXED.items():
            f.write(f"{cid}\t{voice}\t{text}\n")
        for n in names:
            f.write(f"n_{slug(n)}\tassistant\t{n}.\n")
        for n in names + foils:
            f.write(f"t_{slug(n)}\ttask\tCall {n}.\n")
    print(f"{len(names)} option names, {len(foils)} foils, {len(names) * 2 + len(foils) + len(FIXED)} clips")


if __name__ == "__main__":
    main()

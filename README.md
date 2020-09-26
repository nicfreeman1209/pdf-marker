# pdf-marker

Software for efficient batch marking of pdf files. Designed for handwritten mathematics.

Features:
- View and annotate multiple pdfs -- no need to load or convert files individually.  
- Keyboard (WASD keys) and mouse (5 button) are sufficient for exam-style marking.
- Stylus can be used for handwritten annotations.
- Automatically tallies part-marks 
- Automatically checks that part-marks are consistent with a mark scheme (specified via a json format) 
- Generates csv output of marks, part marks, etc

## Instructions for use

Workflow:

1. Place <code>pdf-marker.py</code> into your working directory.
2. Place the raw scripts into a subfolder <code>./1_scripts/</code>
   - There should be precisely one pdf script per candidate.
3. Run pdf-marker.py, press "Load scripts" and wait.
   - This will populate the folder <code>./2_workings/</code> where the program keeps all its internal data. Leave that folder alone!
4. Annotate your pdfs - see below for annotation controls.
5. Press "Output scripts", to write scripts plus annotations to <code>./3_output/</code>
   - The outputted file names will match those inputted in step 2.
   
Optional: Before step 2, place a file called <code>fullmarks.json</code> next to pdf-marker.py.
This file contains your mark scheme in a json format; it enables extra features related to marking and automated tallying/checking.
See below for details.

If extra candidates need to be added later, simply place their pdfs into <code>./1_scripts/</code> and repeat step 3.
Your existing work will not be overwritten.

## Annotation controls

All annotations are made in red. 

- Change page using A (forwards) and D (backwards)
  - Hold shift to skip to the next/previous candidate. Hold control to skip 5 pages or 5 candidates.
- Left mouse adds a circle, click again to increase its size.
- Right mouse adds the word 'justify'.
- Use a stylus to draw or write onto the page.
- Right mouse is used to remove annotations,
  - including those made with a stylus! Each 'connected' use of the stylus is treated as a single annotation.

## Using mark schemes

When a valid <code>fullmarks.json</code> file is present, additional features are enabled.
A margin appears on each page, into which part-marks can be recorded.
Within the margin you can:
- Use the left mouse to add/increase part-marks, right mouse to add a zero mark, right mouse to decrease/remove part-marks.
  - Use <code>shift</code> to add/remove in multiples of 5.
- Use middle mouse to place tally points, right mouse to remove them.
  - Each tally point automatically adds up all part-marks awarded since the previous tally point. 

***The important bit:** Part-marks will now be checked against the mark scheme, to ensure that:*
1. *the correct number of parts are marked per question;* 
2. *no part-mark exceeds the available total for the corresponding part-question;*
3. *all work has been marked.*

*When you click 'Output scripts', each scripts will be checked against the above criteria.
If they do not all pass, you will be automatically shown the first scripts that does not pass.
If they do all pass, the annotated pdfs will be output, alongside various csv files containing candidate marks, part-marks and other useful information.*

Part-marks must be entered into the margin in the correct order. 
Precisely one tally point is expected for each question in the mark scheme, after all its part-marks.
In between tally points, the number of times that part-marks are awarded should match the number of parts of the corresponding question.

- Use the S key to add a vertical strike through a page, to indicate that all work on this page was marked.
- Use the W key to jump to the first candidate on which the checking currently fails. There will be a message explaining the reason.

When there is space on the screen (i.e. if you screen is not in portrait mode), 
text will display the current status of the current candidates marks, against the above criteria.

### Json format for mark schemes

The json format required for the mark scheme is best illustrated by example.
The example in the repository has the structure:
```
[
	["a.i 2", "a.ii 1", "b 5"],
	[". 2"],	
	["a 2", "b 3"]
]
```
This corresponds to 3 questions, one per line.
Q1 has three sub-parts: a.i, a.ii and b, with part-marks 2, 1 and 5 available respectively.
Q2 has no sub-parts and has 2 marks available.
Q3 has two sub-parts: a and b, with 2 and 3 marks available respectively.
Each sub-part must be in the form <code>"xyz n"</code> where <code>xyz</code> is the name of the sub-part (no whitespaces allowed) and <code>n</code> is the number of marks available.
Note that the final question does *not* have a comma at the end of its line, but all other questions do - json is fussy.
(Formally: its a json list of lists of strings, top level is the question number, second level is question sub-parts, strings as described above.)


Mouse buttons 4 and 5 can be used to add forwards/backwards arrows, to indicate if work is marked out of order (right mouse to remove).


## Troubleshooting

Report bugs to the this repository, please attach the <code>pdf-marker.log</code> file.

To restart the process for a single candidate, go into <code>./2_workings/</code> and delete the folder corresponding to the candidate.
Then load in the scripts again - existing work is not overwritten, but the missing folder will be regenerated with a clean copy.







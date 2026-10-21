# Editing your site

Your site is built from the files in this repository. Each time you save a change here on GitHub
(**Commit changes**), the site rebuilds itself and is live at https://sarah-gh60.com a minute or
two later. There is nothing to install.

## Replace a picture

Use a computer for pictures. Before the first time, on a Mac: in Finder, choose **Finder →
Settings → Advanced** and tick **Show all filename extensions**, so you can see a file's whole
name, ending included.

1. On your computer, rename the new picture to **exactly the old picture's name, ending
   included**, for example `hero.jpg`. If your new picture is a PNG, name it `hero.png`.
   (GitHub cannot rename a file while it uploads it, so this comes first.)
2. Here on GitHub, open the folder that holds the old picture (see the tables below).
3. Click **Add file → Upload files**, drag in your picture, and click **Commit changes**. A file
   with the same name is replaced.

If the ending changes (a new `hero.png` for the old `hero.jpg`), delete the old file as well:
open it, click **⋯** at the top right, then **Delete file**, and commit. While both are there,
the site shows the one you changed last, and the run page shows a yellow note.

| Picture | Shape | Good size |
|---|---|---|
| The large picture at the top of a case study (`hero`) | wide, 16:10 | 2400 × 1500 |
| The small picture of a case in the work list (`cover`); phones also show it at the top of the case study | 4:3 | 1200 × 900 |
| Any other picture in a case study | any; wide works best | about 2000 wide |
| Your photo in About (`portrait`) | upright, 4:5 | 1200 × 1500 |
| A painting in Studio | any; the frame follows it | about 2000 wide |
| The large painting detail above the paintings (`hinge-painting`) | wide, 16:10 | 2000 × 1250 |

Keep each picture under about 1 MB. To make a smaller copy on a Mac, open the picture in
Preview, choose **Tools → Adjust Size…**, type the width from the table, and save. JPG suits
photos and screenshots; PNG works too. iPhone photos are often HEIC, which websites cannot
show: open the photo in Preview, choose **File → Export…**, set **Format** to **JPEG**, and
save.

Where the pictures are:

| Picture | Folder |
|---|---|
| Pictures of a case study | `assets/img/work/<folder>` (see the next table) |
| Your photo in About | `assets/img/about` |
| Paintings in Studio | `assets/img/studio` |

| Folder | Case study |
|---|---|
| `design-team` | Building a design team for four Shopify apps |
| `shopify-suite` | One merchant experience across four Built-for-Shopify apps |
| `virtual-care` | Virtual care that works for patients, caregivers and clinicians |
| `design-system` | One token system, three product teams |
| `mobile-commerce` | Mobile checkout and merchant tools |
| `buildings-to-products` | From buildings to products |

To see which picture is which, open the case's text file (`content/projects/<folder>.json`) and
look under `"images"`: each name has an `"alt"` line that describes the picture. When your new
picture shows something different, change that description too; it is what screen readers and
search engines read. The two pictures a case shows in the gallery on the home page are the ones
named under `"plates"` in the same file.

## Change a text

1. Open the file (see the table below) and click the pencil (**Edit this file**).
2. Find the words with search (Ctrl+F, or Cmd+F on a Mac).
3. Change only the words between the double quotes. Keep every `"` `,` `:` `[ ]` and `{ }`
   exactly where it is.
4. Click **Commit changes**.

| What you see on the site | File to open | What to search for |
|---|---|---|
| A case study title | `content/projects/<folder>.json` | `"title"` (see the note below) |
| The line under a case study title | `content/projects/<folder>.json` | `"dek"` |
| The results line in the work list | `content/projects/<folder>.json` | `"register_line"` |
| The three large numbers at the top of a case study | `content/projects/<folder>.json` | `"metrics"` |
| "The 60-second version" | `content/projects/<folder>.json` | `"tldr"` |
| Captions of the plates on the home page | `content/projects/<folder>.json` | `"plates"` |
| Any other text in a case study | `content/projects/<folder>.json` | a few words of that text |
| A case study's title in the browser tab, and the description Google shows | `content/projects/<folder>.json` | `"seo"` |
| The work list on the home page (title, sector, role, years, results) | the case's own file | the words, as above |
| The charts and tables in Leadership (hiring funnel, budget, capacity plan, scorecard, monthly brief, the design week, roadmap, career ladder, cadence) | `content/projects/design-team.json` | a few words of that text |
| Other texts on the home page: intro, the rest of Leadership, Career, About, Studio, Contact | `index.html` | a few words of that text |
| The home page's title in the browser tab, and the description Google shows | `index.html` | `<title>` and `name="description"` at the very top; the `og:title` and `og:description` lines just below are what link previews show |
| Your email address | `content/site.json` | `"email"` (the site changes it everywhere it appears) |

A few things to know:

- **Case study titles** are written twice: as `"title"` and, just below, as `"title_html"`, where
  the word between `<em>` and `</em>` is shown in italics. Change both the same way. If you
  change only `"title"`, the new title still appears everywhere, with the same word in italics
  while it is still in the title. If `"seo"` has its own `"title"`, that is the one in the
  browser tab: change it too.
- **Quotation marks:** the quotes around each name and each text must be straight double quotes
  (`"`), as they are now. Inside a text, use curly quotes “like this”: a straight double quote
  ends the text early. Apostrophes (') are fine. Text pasted from Notes or Word can bring curly
  quotes along, so paste only the words, between the quotes that are already there.
- **In `index.html`**, change only words: the text between `>` and `<`, the description between
  the quotes after `alt=` and, at the very top, the words between the quotes after `content=`.
  Inside those quotes, use ’ “ ” and never a straight `"`. Leave everything else inside `< >` as
  it is.
- **In `index.html`, the text between a line such as `<!-- WORK:START -->` and its matching
  `<!-- WORK:END -->`** (also `PLATES`, `INDEX` and `ARTIFACT`) is filled in from the case files on
  every save, so a change there does not last. Change it in the case file instead.
- Longer or shorter texts are fine. The design looks best when a new text is about as long as
  the one it replaces.

## Paintings and the About photo

- **A new painting picture:** upload it to `assets/img/studio/` under the painting's file name:
  `low-tide-steveston`, `fog-over-the-fraser`, `courtyard-at-noon` or `garry-point-after-rain`.
  The frame follows the shape of your picture. The file name never shows on the site, so it can
  stay the same when the title changes.
- **The large painting detail above the paintings** is `hinge-painting` in the same folder. Its
  frame is always wide (16:10), and a picture of another shape is cropped to fit. The app screen
  beside it is `assets/img/work/shopify-suite/setup-after.jpg`, which also appears in that case
  study.
- **A painting's title, medium and size** are in `index.html`: search for the painting's title.
  The title is between `<cite>` and `</cite>`; the medium and size are on the next two lines. The
  title also starts the picture description, after `alt=` in the long line above; change it there
  too.
- **Your About photo:** upload it to `assets/img/about/` as `portrait.jpg` (or `portrait.png`).
  Upright photos work best; the site shows it in a 4:5 frame. Its description is in `index.html`:
  search for `portrait__img`, then change the words after `alt=` on that line.

## Link previews

When someone shares a link to your site (on LinkedIn, in Slack or in a message), a preview card
shows with it. Each card was made for the page's texts and cover as they are now. When you change
a case study's title, results line, sector, years, role or cover, its link preview switches by
itself to the case's `hero` picture. When you change the words at the top of the home page, the
home page's link preview switches to your About photo.

## Did it work?

Open the **Actions** tab of this repository. Every save starts a new run at the top of the list.

- **Green tick:** your change is live a minute or two later. Reload the site; if it still shows
  the old version, reload once more while holding Shift.
- **Green tick, but a picture did not change:** click the run. A yellow note names the file and
  says what to do, for example when a file's name matches no picture, when it is an iPhone HEIC
  file, when two files stand for one picture, or when a picture is very large.
- **Red cross:** nothing went live, and the site keeps its previous version. Click the run: the
  red note names the file and the line. Usually a quote or a comma went missing. Open that file,
  fix the line, and commit again.
- **Grey (Cancelled):** you saved several times in a row, and a newer run took its place. Only
  the newest run matters.

import re

import gradio as gr, pandas as pd
from thefuzz import fuzz, process
from tqdm import tqdm


app = gr.Blocks()


def normalize_company_names(x: str):
    '''Clean company names and prepare for fuzzy matching'''
    # lowercasing
    x = str(x).lower().strip()
    # remove special characters
    x = re.sub(r'[^a-z0-9 ]', '', x)
    # remove trailing artifacts
    x = re.sub(r' (q[1-4].*?|old|adr)$', '', x)  # SA / Compustat
    x = re.sub(r' (cl ?a|cl ?b|redh)$', '', x)  # ExecuComp
    x = re.sub(r'-old$', '', x)
    # remove legal forms
    x = re.sub(
        r' (public limited company|public limited|limited|unlimited|partnership|incorporation|incorporated|corporation|plc|pbc|ltd|inc|corp|llc|lp)$',
        '', x
    )
    # normalize other frequent error cases
    x = re.sub(r' hldgs', ' holdings', x)
    x = re.sub(r' co$', ' company', x)
    x = re.sub(r'^the ', '', x)
    x = re.sub(r' and ', ' ', x)
    # remove of whitespaces
    x = x.replace(' ', '')
    return x


def normalize_person_names(x):
    '''Clean company names and prepare for fuzzy matching'''
    # remove special characters
    x = re.sub(r'[^A-Za-z0-9 ]', '', x)
    # remove title
    x = re.sub(
        r' (Economics|PharmD|CISA|MPPM|Hons|Hon|BBA|MBA|JD|MIM|PhD|Hon|FCPA|CFA|CPA|FCA|CMA|MAI|BSc|BSC|MSc|MSC|ESQ|MS|BA|CA|BE|AM|PE|AO|MD)',
        '', x
    )
    # lowercasing
    x = str(x).lower().strip()
    # sort names alphabetically
    x = x.split()
    x.sort()
    x = ''.join(x)
    return x


def fuzzy_match(query: pd.DataFrame, q_name_norm: str,
                db: pd.DataFrame, db_name_norm: str, db_name_id: str, db_name: str,
                q_fy: str = None, q_qtr: str = None, db_fy: str = None, db_qtr: str = None):
    '''Fuzzy match nearest neighbours for query in (filtered) database based on Levenshtein Distance

    :param pd.DataFrame query:
        DataFrame from which to query
    :param str q_name_norm:
        Column name of normalized string column in query

    :param pd.DataFrame db:
        DataFrame in which to search for match
    :param str db_name_norm:
        Column name of normalized string column in database
    :param str db_name_id:
        Column name of id column in database
    :param str db_name:
        Column name of string column in database

    :param str q_fy:
        Column name of fiscal year column in query (for filtering)
    :param str q_qtr:
        Column name of fiscal quarter column in query (for filtering)
    :param str db_fy:
        Column name of fiscal year column in database (for filtering)
    :param str db_qtr:
        Column name of fiscal quarter column in database (for filtering)

    :return pd.Series neihbours:
        Series of tuples of the form (nearest neighbour:str, similarity score:int, gvkey:int)

    '''

    def retrieve_nn(x: pd.DataFrame, db: pd.DataFrame):
        ''' Fuzzy match nearest neighbour for query string '''

        # limit fuzzy match to relevant time interval
        if q_fy and q_qtr and db_fy and db_qtr:
            db = db[(db[db_fy] == x[q_fy]) & (db[db_qtr] == x[q_qtr])]
        elif q_fy and db_fy:
            db = db[(db[db_fy] == x[q_fy])]

        # retrieve nearest neighbour
        try:
            nn, score, _ = process.extractOne(x[q_name_norm], db[db_name_norm], scorer=fuzz.ratio)
            id = db[db[db_name_norm]==nn][db_name_id]
            id = id.item() if len(id)==1 else ', '.join(str(x) for x in id.tolist())
            name = db[db[db_name_norm]==nn][db_name]
            name = name.item() if len(name)==1 else ', '.join(str(x) for x in name.tolist())
            return (nn, score, id, name)
        except:
            return (None, None, None, None)

    tqdm.pandas()
    return query.progress_apply(lambda x: retrieve_nn(x, db), axis=1)


def match(p_file, p_id, p_name, p_year, p_qtr,
          s_file, s_id, s_name, s_year, s_qtr,
          norm_person=False, out='out', progress=gr.Progress(track_tqdm=True)):
    
    # input data
    p_file = p_file.name
    s_file = s_file.name
    if p_file[-4:] == '.csv':
        pri = pd.read_csv(p_file)
    elif p_file[-4:] == '.dta':
        pri = pd.read_stata(p_file)
    else:
        raise ValueError("Please input either .csv or .dta")
    if s_file[-4:] == '.csv':
        sec = pd.read_csv(s_file)
    elif s_file[-4:] == '.dta':
        sec = pd.read_stata(s_file)
    else:
        raise ValueError("Please input either .csv or .dta")

    # normalize names
    fn_norm = normalize_person_names if norm_person == "Person" else normalize_company_names
    p_name_norm = f'{p_name}_norm'
    s_name_norm = f'{s_name}_norm'
    pri = pri.assign(**{p_name_norm: pri[p_name].map(lambda x: fn_norm(x))})
    sec = sec.assign(**{s_name_norm: sec[s_name].map(lambda x: fn_norm(x))})

    # match
    pri['nn_match'], pri['nn_score'], pri[f'nn_{s_id}'], pri[f'nn_{s_name}'] = \
        zip(*fuzzy_match(pri, p_name_norm,
                         sec, s_name_norm, s_id, s_name,
                         q_fy=p_year, q_qtr=p_qtr, db_fy=s_year, db_qtr=s_qtr))

    # output data
    if p_file[-4:] == '.csv':
        out_path = 'output.csv'
        pri.to_csv(out_path, sep=';')
    else:
        out_path = 'output.dta'
        pri.to_stata(out_path, version=118)

    return out_path


with app:
    gr.Markdown("# Fuzzy Name Matcher")
    with gr.Row():
        with gr.Column():
            P_FILE = gr.File(label="Primary file")
            P_ID = gr.Textbox(lines=1, value="", label="ID column", placeholder="Insert name of ID column here...")
            P_NAME = gr.Textbox(lines=1, value="", label="Name column", placeholder="Insert name of entity name column here...")
            P_YEAR = gr.Textbox(lines=1, value="", label="Year column (optional)", placeholder="Insert name of year column here...")
            P_QTR = gr.Textbox(lines=1, value="", label="Quarter column (optional)", placeholder="Insert name of quarter column here...")
        with gr.Column():
            S_FILE = gr.File(label="Secondary file")
            S_ID = gr.Textbox(lines=1, value="", label="ID column", placeholder="Insert name of ID column here...")
            S_NAME = gr.Textbox(lines=1, value="", label="Name column", placeholder="Insert name of entity name column here...")
            S_YEAR = gr.Textbox(lines=1, value="", label="Year column (optional)", placeholder="Insert name of year column here...")
            S_QTR = gr.Textbox(lines=1, value="", label="Quarter column (optional)", placeholder="Insert name of quarter column here...")
        with gr.Column():
            with gr.Accordion("Open Instruction Manual", open=False):
                gr.Markdown("[instructions.pdf](https://github.com/simonschoe/fuzzy-name-match)")
            fn_norm = gr.Radio(label="Choose entity type", choices=["Firm", "Person"], value="Firm")
            compute_bt = gr.Button("Start Matching")
            res = gr.File(interactive=False, label="Download")
        compute_bt.click(match, inputs=[P_FILE, P_ID, P_NAME, P_YEAR, P_QTR, S_FILE, S_ID, S_NAME, S_YEAR, S_QTR, fn_norm], outputs=[res])

app.queue().launch(server_name='0.0.0.0')

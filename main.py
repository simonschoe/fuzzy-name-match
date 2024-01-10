""" Fuzzy name matcher for entity matching """
import re

import gradio as gr
import pandas as pd
from rapidfuzz import fuzz, process
from tqdm import tqdm

app = gr.Blocks()


def normalize_company_names(x: str, geography: str = 'us'):
    '''Clean company names and prepare for fuzzy matching'''

    if geography == 'us':
        legal_forms = re.compile(r' (public limited company|public limited|limited|unlimited|partnership|incorporation|incorporated|corporation|plc|pbc|ltd|inc|corp|llc|lp|co|company|companies|hldgs|holdings|holding)$')
    elif geography == 'int':
        legal_forms = re.compile(r' (public limited company|public limited|limited|unlimited|partnership|incorporation|incorporated|corporation|plc|pbc|ltd|inc|corp|llc|lp|co|company|companies|hldgs|holdings|holding|ab|ag|as|asa|berhad|bhd|bv|cva|esp|jsc|jscb|kgaa|kpsc|ksc|kscp|nv|oyj|pcl|pt|publ|spa|sae|sa|saa|saog|se|spv|tbk)$')

    # lowercasing
    x = str(x).lower().strip()
    # remove special characters
    x = re.sub(r'[^a-z0-9 ]', '', x)
    # remove trailing artifacts
    x = re.sub(r' (q[1-4].*?|old|adr)$', '', x)  # SA / Compustat
    x = re.sub(r' (cl ?a|cl ?b|redh)$', '', x)  # ExecuComp
    x = re.sub(r'-old$', '', x)
    # iteratively remove legal forms from end of string
    while legal_forms.search(x):
        x = re.sub(legal_forms,'', x).strip()
    # normalize other frequent error cases
    if geography == 'us':
        x = re.sub(r'^the ', '', x)
    elif geography == 'int':
        x = re.sub(r'^(the|pt) ', '', x)
    x = re.sub(r' and ', ' ', x)
    # remove of whitespaces
    x = x.replace(' ', '')
    return x


def normalize_person_names(x: str):
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
            entity_id = db[db[db_name_norm]==nn][db_name_id]
            entity_id = str(id.item()) if len(id)==1 else ', '.join(str(x) for x in entity_id.tolist())
            name = db[db[db_name_norm]==nn][db_name]
            name = name.item() if len(name)==1 else ', '.join(str(x) for x in name.tolist())
            return (nn, score, entity_id, name)
        except Exception:
            return (None, None, None, None)

    tqdm.pandas()
    return query.progress_apply(lambda x: retrieve_nn(x, db), axis=1)


def match(p_file, p_id, p_name, p_year, p_qtr,
          s_file, s_id, s_name, s_year, s_qtr,
          normalization, progress=gr.Progress(track_tqdm=True)):
    """ Match entities in primary file to entities in secondary file """

    try:
        # input data
        p_file = p_file.name
        s_file = s_file.name
        if p_file[-4:] == '.csv':
            pri = pd.read_csv(p_file, sep=None)
        elif p_file[-4:] == '.dta':
            pri = pd.read_stata(p_file)
        else:
            raise ValueError("Please input either .csv or .dta")
        if s_file[-4:] == '.csv':
            sec = pd.read_csv(s_file, sep=None)
        elif s_file[-4:] == '.dta':
            sec = pd.read_stata(s_file)
        else:
            raise ValueError("Please input either .csv or .dta")

        # normalize names
        p_name_norm = f'{p_name}_norm'
        s_name_norm = f'{s_name}_norm'
        if normalization == 'Firm (US)':
            pri = pri.assign(**{p_name_norm: pri[p_name].map(lambda x: normalize_company_names(x, geography='us'))})
            sec = sec.assign(**{s_name_norm: sec[s_name].map(lambda x: normalize_company_names(x, geography='us'))})
        elif normalization == 'Firm (Int)':
            pri = pri.assign(**{p_name_norm: pri[p_name].map(lambda x: normalize_company_names(x, geography='int'))})
            sec = sec.assign(**{s_name_norm: sec[s_name].map(lambda x: normalize_company_names(x, geography='int'))})
        elif normalization == 'Person':
            pri = pri.assign(**{p_name_norm: pri[p_name].map(normalize_person_names)})
            sec = sec.assign(**{s_name_norm: sec[s_name].map(normalize_person_names)})

        # match
        pri['nn_match'], pri['nn_score'], pri[f'nn_{s_id}'], pri[f'nn_{s_name}'] = \
            zip(*fuzzy_match(pri, p_name_norm, sec, s_name_norm, s_id, s_name,
                             q_fy=p_year, q_qtr=p_qtr, db_fy=s_year, db_qtr=s_qtr))

        # output data
        if p_file[-4:] == '.csv':
            out_path = 'merge.csv'
            pri.to_csv(out_path, sep=';')
        else:
            out_path = 'merge.dta'
            pri.to_stata(out_path, version=118)

        return out_path

    except Exception as e:
        raise gr.Error(e)

with app:
    gr.Markdown("# Fuzzy Name Matcher")
    with gr.Row():
        with gr.Column():
            P_FILE = gr.File(label="Primary file", file_types=[".csv", ".dta"])
            P_ID = gr.Textbox(lines=1, value="", label="ID column", placeholder="Insert name of ID column here...")
            P_NAME = gr.Textbox(lines=1, value="", label="Name column", placeholder="Insert name of entity name column here...")
            P_YEAR = gr.Textbox(lines=1, value="", label="Year column (optional)", placeholder="Insert name of year column here...")
            P_QTR = gr.Textbox(lines=1, value="", label="Quarter column (optional)", placeholder="Insert name of quarter column here...")
        with gr.Column():
            S_FILE = gr.File(label="Secondary file", file_types=[".csv", ".dta"])
            S_ID = gr.Textbox(lines=1, value="", label="ID column", placeholder="Insert name of ID column here...")
            S_NAME = gr.Textbox(lines=1, value="", label="Name column", placeholder="Insert name of entity name column here...")
            S_YEAR = gr.Textbox(lines=1, value="", label="Year column (optional)", placeholder="Insert name of year column here...")
            S_QTR = gr.Textbox(lines=1, value="", label="Quarter column (optional)", placeholder="Insert name of quarter column here...")
        with gr.Column():
            with gr.Accordion("Open Instruction Manual", open=False):
                gr.Markdown("[README.md](https://github.com/simonschoe/fuzzy-name-match/blob/master/README.md)")
            norm = gr.Radio(label="Choose entity type", choices=["Firm (US)", "Firm (Int)", "Person"], value="Firm (US)")
            with gr.Column():
                compute_bt = gr.Button("Start Matching", variant='primary', scale=2)
                stop_bt = gr.Button("Stop Program", variant='secondary', scale=1)
            res = gr.File(interactive=False, label="Merged file")
        compute_event = compute_bt.click(fn=match, inputs=[P_FILE, P_ID, P_NAME, P_YEAR, P_QTR, S_FILE, S_ID, S_NAME, S_YEAR, S_QTR, norm], outputs=[res])
        stop_bt.click(fn=None, inputs=None, outputs=None, cancels=[compute_event])

# sharable
# app.queue(max_size=1).launch(share=True)
# access from docker container
app.queue(max_size=1).launch(server_name='0.0.0.0', server_port=7878)

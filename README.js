class encn_KBBI {
    constructor(options) {
        this.options = options;
        this.maxexample = 2;
        this.word = '';
    }

    async displayName() {
        return 'Kamus Besar Bahasa Indonesia';
    }

    setOptions(options) {
        this.options = options;
        this.maxexample = options.maxexample;
    }

    async findTerm(word) {
        this.word = word;
        let results = await Promise.all([this.findKBBI(word)]);
        return [].concat(...results).filter(x => x);
    }

    async findKBBI(word) {
        const maxexample = this.maxexample;
        if (!word) return [];

        let base = 'https://kbbi.kemdikbud.go.id/entri/';
        let url = base + encodeURIComponent(word);
        let doc = '';
        try {
            let data = await api.fetch(url);
            let parser = new DOMParser();
            doc = parser.parseFromString(data, 'text/html');
            let definitions = getKBBIDefinitions(doc);
            return definitions;
        } catch (err) {
            return [];
        }

        function getKBBIDefinitions(doc) {
            let notes = [];

            // Identify the definition section
            let defNodes = doc.querySelectorAll('.container .daftar');

            if (!defNodes || !defNodes.length) return notes;

            // Get headword
            let expression = T(doc.querySelector('.container .lema .h2font'));

            // Prepare definitions
            let definitions = [];
            for (const defNode of defNodes) {
                let definition = T(defNode);
                definitions.push(`<span class="tran">${definition}</span>`);
            }

            let css = `
                <style>
                    span.tran {margin:0; padding:0; color: #0d47a1;}
                </style>`;

            notes.push({
                css,
                expression,
                definitions,
                audios: [] // No audio provided
            });

            return notes;
        }

        function T(node) {
            if (!node) return '';
            else return node.innerText.trim();
        }
    }
}

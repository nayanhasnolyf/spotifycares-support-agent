import json
import glob

for f in glob.glob('data/labels/annotation/machine/training/*.jsonl'):
    try:
        with open(f, 'r', encoding='utf-8') as file:
            lines = file.readlines()
        
        valid_lines = []
        for line in lines:
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                if data.get('status') != 'failure':
                    valid_lines.append(line.strip())
            except json.JSONDecodeError:
                pass
                
        with open(f, 'w', encoding='utf-8') as file:
            file.write('\n'.join(valid_lines) + '\n')
            
        print(f"Cleaned {f}")
    except Exception as e:
        print(f"Failed to clean {f}: {e}")
